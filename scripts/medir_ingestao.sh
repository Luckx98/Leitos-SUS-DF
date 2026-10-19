#!/usr/bin/env bash
# Medição do ADR 0002: custo e latência dos caminhos de ingestão sobre a carga completa.
#
# Pré-requisito: a origem com a carga completa (MODO=completo docker compose up).
# Uso: scripts/medir_ingestao.sh [COMPETENCIA_NOVA]   (padrão: 2026-08)
#
# Fases, uma por vez para caber na memória de um notebook:
#   1. Lote inicial: exporta a origem inteira para lote.*. É também o custo de
#      cada execução da opção nula (recarga completa agendada).
#   2. Snapshot do CDC: Debezium + Redpanda + consumidor trazem a origem inteira
#      para cdc.*.
#   3. Competência nova (DF e GO): latência do CDC até a reconciliação e custo
#      do lote incremental (exportação + janela + compactação).
# Durante as fases, a memória e a CPU dos containers são amostradas a cada 2 s.
set -euo pipefail

COMPETENCIA="${1:-2026-08}"
DC="docker compose --profile e2"
SAIDA="medicoes/e2/ingestao_$(date +%F).txt"
AMOSTRAS="$(mktemp)"
mkdir -p medicoes/e2
exec > >(tee "$SAIDA") 2>&1

amostrar() {  # amostrar <arquivo>: grava "fase nome memória_MiB cpu%" até ser morto
    while true; do
        docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.CPUPerc}}' 2>/dev/null \
            | awk -v fase="$FASE" '{m=$2; u=m; gsub(/[0-9.]/,"",u); gsub(/[A-Za-z]/,"",m);
                  if (u=="GiB") m*=1024; if (u=="KiB") m/=1024; gsub("%","",$NF); print fase, $1, m, $NF}' >> "$1"
        sleep 2
    done
}

resumo_recursos() {  # pico de memória e CPU média por container numa fase
    echo "   pico de memória / CPU média por container:"
    awk -v fase="$1" '$1==fase {if ($3>pico[$2]) pico[$2]=$3; cpu[$2]+=$4; n[$2]++}
         END {for (c in pico) printf "     %-28s %7.0f MiB  %5.1f%%\n", c, pico[c], cpu[c]/n[c]}' "$AMOSTRAS" | sort
}

contar_iceberg() {  # contar_iceberg <namespace.tabela>
    $DC run --rm --no-deps lote python -c "
from lakehouse.config import ConfigLakehouse; from lakehouse.catalogo import abrir_catalogo
t = abrir_catalogo(ConfigLakehouse.do_ambiente()).load_table('$1')
s = t.current_snapshot(); print(int(s.summary.get('total-records') or 0) if s else 0)" 2>/dev/null | tail -1
}

origem() { $DC exec -T postgres psql -U "${POSTGRES_USER:-leitos}" -d "${POSTGRES_DB:-leitos}" -tAc "$1"; }

echo "# Medição dos caminhos de ingestão — $(date '+%F %T %Z')"
echo "# Máquina: $(nproc) CPUs, $(free -h | awk '/^Mem:/ {print $2}') de RAM"
echo "# Origem: $(origem 'SELECT count(*) FROM internacao') internações, $(origem 'SELECT count(*) FROM carga') cargas"

FASE=lote_inicial; amostrar "$AMOSTRAS" & AMOSTRADOR=$!
trap 'kill $AMOSTRADOR 2>/dev/null || true; rm -f "$AMOSTRAS"' EXIT

echo; echo "== Fase 1: lote inicial (= custo de cada recarga completa da opção nula)"
$DC up -d seaweedfs >/dev/null 2>&1
$DC run --rm lakehouse-init >/dev/null 2>&1
inicio=$(date +%s.%N)
$DC run --rm --no-deps lote 2>&1 | grep -E "lakehouse\.(lote|brutos):" | sed -E 's/^.*INFO lakehouse\.[a-z]+: /   /'
echo "   tempo total: $(echo "$(date +%s.%N) - $inicio" | bc | xargs printf '%.0f') s"
kill $AMOSTRADOR; resumo_recursos lote_inicial

echo; echo "== Fase 2: snapshot do CDC (origem inteira para cdc.*)"
FASE=cdc_snapshot; amostrar "$AMOSTRAS" & AMOSTRADOR=$!
alvo=$(origem 'SELECT count(*) FROM internacao')
inicio=$(date +%s)
$DC up -d redpanda debezium cdc >/dev/null 2>&1
while true; do
    n=$(contar_iceberg cdc.internacao)
    decorrido=$(( $(date +%s) - inicio ))
    echo "   ${decorrido}s: cdc.internacao = $n / $alvo"
    [ "$n" -ge "$alvo" ] && break
    [ "$decorrido" -gt 5400 ] && { echo "   desisti depois de 90 min"; break; }
    sleep 30
done
echo "   tempo até cdc.internacao completa: ${decorrido} s"
$DC logs debezium 2>&1 | grep -E "Snapshot (completed|ended)" | sed -E 's/^.*\| /   debezium: /' | cut -c1-140 | tail -2
kill $AMOSTRADOR; resumo_recursos cdc_snapshot

echo; echo "== Fase 3: competência nova ($COMPETENCIA, DF e GO)"
FASE=competencia_nova; amostrar "$AMOSTRAS" & AMOSTRADOR=$!
inicio=$(date +%s)
MODO=completo UFS=DF,GO COMPETENCIA_INICIO="$COMPETENCIA" COMPETENCIA_FIM="$COMPETENCIA" \
    $DC run --rm --no-deps loader 2>&1 | grep -E "carga: " | sed -E 's/^.*INFO loader.carga: /   origem: /'
fim_carga=$(date +%s)
echo "   loader: $((fim_carga - inicio)) s"
alvo=$(origem 'SELECT count(*) FROM internacao')
until [ "$(contar_iceberg cdc.internacao)" -ge "$alvo" ]; do sleep 3; done
echo "   CDC: cdc.internacao com as $alvo internações $(( $(date +%s) - fim_carga )) s depois do fim da carga"
inicio=$(date +%s.%N)
$DC run --rm --no-deps lote 2>&1 | grep -E "lakehouse\.(lote|compactar):|janela:|maturidade" | sed -E 's/^.*INFO lakehouse\.[a-z]+: /   /'
echo "   lote incremental (exportação + janela + compactação): $(echo "$(date +%s.%N) - $inicio" | bc | xargs printf '%.0f') s"
kill $AMOSTRADOR; resumo_recursos competencia_nova

echo; echo "== Reconciliação final"
$DC run --rm --no-deps lote python -m lakehouse.reconciliar 2>&1 | grep -vE "Container" | sed 's/^/   /'
echo; echo "Resultado gravado em $SAIDA"
