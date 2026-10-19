"""Demonstração da semântica de entrega: força reexecuções e mostra o efeito nos dados.

    scripts/demo_semantica.sh   (para o serviço cdc, roda isto e o religa)

Passos:
1. Estado inicial: reconciliação de cdc.* com a origem.
2. Reexecução do lote: roda o exportador de novo; a marca d'água no snapshot
   faz com que nada seja regravado.
3. Releitura forçada do CDC com deduplicação: o consumidor ignora o offset
   gravado e relê os tópicos desde o início, como num reenvio em massa do
   Debezium. Todas as linhas já existem: nenhuma é gravada.
4. A mesma releitura sem deduplicação: entrega pelo menos uma vez pura.
   Cada linha relida vira uma duplicata, e a reconciliação acusa.
5. Viagem no tempo: as tabelas cdc.* voltam ao snapshot de antes do passo 4.
"""

from __future__ import annotations

import logging
import sys

from lakehouse.catalogo import abrir_catalogo
from lakehouse.cdc import ConsumidorCdc
from lakehouse.config import ConfigLakehouse
from lakehouse.esquemas import TABELAS
from lakehouse.lote import exportar
from lakehouse.reconciliar import reconciliar

log = logging.getLogger("lakehouse.demo")


def titulo(texto: str) -> None:
    log.info("")
    log.info("== %s", texto)


def releitura(config: ConfigLakehouse, dedup: bool) -> tuple[int, int, int]:
    consumidor = ConsumidorCdc(config, dedup=dedup, do_inicio=True)
    consumidor.executar(linhas_por_lote=50_000, segundos_por_lote=5, sair_ocioso=10)
    est = consumidor.estatistica.values()
    return sum(e.eventos for e in est), sum(e.gravadas for e in est), sum(e.duplicadas for e in est)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("lakehouse.cdc").setLevel(logging.WARNING)
    config = ConfigLakehouse.do_ambiente()
    catalogo = abrir_catalogo(config)

    titulo("1. Estado inicial (cdc.* contra a origem)")
    if not reconciliar(config, caminhos=("cdc",)):
        log.error("o estado inicial já diverge; rode o consumidor até reconciliar antes da demonstração")
        return 1
    antes = {t: catalogo.load_table(f"cdc.{t}").current_snapshot().snapshot_id for t in TABELAS}

    titulo("2. Reexecução do lote")
    linhas = sum(r["linhas"] for r in exportar(config))
    log.info("linhas regravadas pelo lote: %d", linhas)

    titulo("3. Releitura forçada do CDC desde o offset 0, COM deduplicação")
    eventos, gravadas, duplicadas = releitura(config, dedup=True)
    log.info("eventos relidos: %d | linhas gravadas: %d | duplicatas descartadas: %d", eventos, gravadas, duplicadas)
    reconciliar(config, caminhos=("cdc",))

    titulo("4. A mesma releitura SEM deduplicação (pelo menos uma vez pura)")
    eventos, gravadas, duplicadas = releitura(config, dedup=False)
    log.info("eventos relidos: %d | linhas gravadas: %d | duplicatas descartadas: %d", eventos, gravadas, duplicadas)
    reconciliar(config, caminhos=("cdc",))

    titulo("5. Viagem no tempo: cdc.* de volta ao snapshot anterior ao passo 4")
    for tabela, snapshot_id in antes.items():
        iceberg = catalogo.load_table(f"cdc.{tabela}")
        if iceberg.current_snapshot().snapshot_id != snapshot_id:
            iceberg.manage_snapshots().rollback_to_snapshot(snapshot_id).commit()
    ok = reconciliar(config, caminhos=("cdc",))
    log.info("")
    log.info("resultado: %s", "cdc.* reconciliado de novo com a origem" if ok else "DIVERGÊNCIA após a restauração")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
