#!/usr/bin/env bash
# Demonstração do CDC: uma mudança na origem aparece em cdc.* sem rodar nada à mão.
#
# Uso (com o perfil e2 no ar: docker compose --profile e2 up -d):
#   scripts/demo_cdc.sh              # carrega DF 02/2025 do FTP do DATASUS
#   scripts/demo_cdc.sh GO 2025-03   # outra UF e competência
#
# A origem é insert-only: a "mudança" é uma competência nova carregada pelo loader,
# que só faz INSERT. O script mostra os eventos chegando ao Redpanda e as linhas
# chegando ao Iceberg, e mede o tempo até a reconciliação fechar.
set -euo pipefail

UF="${1:-DF}"
COMPETENCIA="${2:-2025-02}"
DC="docker compose --profile e2"
SAIDA="$(mktemp)"
trap 'rm -f "$SAIDA"' EXIT

eventos_no_topico() {
    $DC exec -T redpanda rpk topic describe leitos.public.internacao -p 2>/dev/null | awk 'NR>1 {print $NF}'
}

echo "== 1. Antes: eventos de internação no Redpanda = $(eventos_no_topico)"
ultima=$($DC exec -T postgres psql -U "${POSTGRES_USER:-leitos}" -d "${POSTGRES_DB:-leitos}" -tAc "SELECT coalesce(max(id_carga), 0) FROM carga")
echo "   última carga na origem: $ultima"

echo "== 2. Mudança na origem: carregando $UF $COMPETENCIA (INSERT de uma competência nova)"
inicio=$(date +%s)
MODO=completo UFS="$UF" COMPETENCIA_INICIO="$COMPETENCIA" COMPETENCIA_FIM="$COMPETENCIA" \
    $DC run --rm --no-deps loader 2>&1 | grep -E "carga: .*${UF}" | sed -E 's/^.*INFO loader.carga: /   /'
carregado=$(date +%s)
nova=$($DC exec -T postgres psql -U "${POSTGRES_USER:-leitos}" -d "${POSTGRES_DB:-leitos}" -tAc \
    "SELECT max(id_carga) FROM carga WHERE fonte = 'SIH_RD' AND status = 'concluida'")
echo "   carga do SIH na origem: id_carga $nova (loader levou $((carregado - inicio)) s)"
echo "   eventos de internação no Redpanda agora = $(eventos_no_topico)"

echo "== 3. Esperando a carga $nova aparecer em cdc.internacao"
for tentativa in $(seq 1 60); do
    if $DC run --rm --no-deps cdc python -m lakehouse.reconciliar --caminho cdc --carga "$nova" >"$SAIDA" 2>&1; then
        echo "   reconciliado $(( $(date +%s) - carregado )) s depois do fim da carga:"
        grep -E "^(internacao|leito|carga|estabelecimento)" "$SAIDA" | sed 's/^/   /'
        exit 0
    fi
    sleep 5
done
echo "   não reconciliou em 5 minutos:"; cat "$SAIDA"; exit 1
