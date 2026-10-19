"""Reconciliação: compara, por tabela e por carga, a origem com lote.* e cdc.*.

    python -m lakehouse.reconciliar            # todas as cargas
    python -m lakehouse.reconciliar --carga 9  # só uma carga
    python -m lakehouse.reconciliar --caminho cdc

Também mede duplicatas pela chave e a latência (commit na origem -> Iceberg).
Termina com código 1 se algum caminho divergir da origem.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter

import duckdb
import psycopg

from lakehouse.catalogo import abrir_catalogo
from lakehouse.cdc import CHAVES
from lakehouse.config import ConfigLakehouse
from lakehouse.esquemas import TABELAS

log = logging.getLogger("lakehouse.reconciliar")

COLUNA_CARGA = {t: "id_carga" for t in TABELAS} | {"estabelecimento": "primeira_carga"}


def contar_origem(conexao: psycopg.Connection, tabela: str, carga: int | None) -> Counter:
    coluna = COLUNA_CARGA[tabela]
    filtro = "WHERE {c} = %s".format(c=coluna) if carga else ""
    linhas = conexao.execute(f"SELECT {coluna}, count(*) FROM {tabela} {filtro} GROUP BY 1",
                             (carga,) if carga else None).fetchall()
    return Counter(dict(linhas))


def medir_iceberg(con: duckdb.DuckDBPyConnection, catalogo, namespace: str, tabela: str,
                  carga: int | None) -> tuple[Counter, int, int, float] | None:
    """Conta, deduplica e mede a latência no motor do DuckDB, sobre o Arrow da varredura:
    nenhuma chave vira objeto Python (3,67 milhões de tuplas num set estourava a memória)."""
    coluna = COLUNA_CARGA[tabela]
    iceberg = catalogo.load_table(f"{namespace}.{tabela}")
    if iceberg.current_snapshot() is None:
        return None
    campos = tuple(dict.fromkeys((coluna, *CHAVES[tabela], "_commit_em", "_ingerido_em")))
    varredura = iceberg.scan(selected_fields=campos, **({"row_filter": f"{coluna} == {carga}"} if carga else {}))
    con.register("_varredura", varredura.to_arrow())
    try:
        contagem = Counter(dict(con.execute(f"SELECT {coluna}, count(*) FROM _varredura GROUP BY 1").fetchall()))
        chave = ", ".join(CHAVES[tabela])
        total, duplicatas, media_s = con.execute(f"""
            SELECT count(*), count(*) - count(DISTINCT ({chave})),
                   avg(epoch(_ingerido_em) - epoch(_commit_em))
            FROM _varredura
        """).fetchone()
    finally:
        con.unregister("_varredura")
    return contagem, total, duplicatas, media_s or 0


def reconciliar(config: ConfigLakehouse, carga: int | None = None,
                caminhos: tuple[str, ...] = ("lote", "cdc")) -> bool:
    catalogo = abrir_catalogo(config)
    con = duckdb.connect()
    ok = True
    with psycopg.connect(config.database_url) as conexao:
        for tabela in TABELAS:
            origem = contar_origem(conexao, tabela, carga)
            total_origem = sum(origem.values())
            partes = [f"{tabela:<23} origem {total_origem:>9}"]
            for namespace in caminhos:
                resultado = medir_iceberg(con, catalogo, namespace, tabela, carga)
                if resultado is None:
                    partes.append(f"{namespace} {0:>9}")
                    ok &= total_origem == 0
                    continue
                contagem, total, duplicatas, media_s = resultado
                igual = contagem == origem and duplicatas == 0
                ok &= igual
                partes.append(f"{namespace} {total:>9} dup {duplicatas:>5} lat.média {media_s:>8.1f}s "
                              f"{'ok' if igual else 'DIVERGE'}")
            log.info(" | ".join(partes))
    con.close()
    return ok


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    argumentos = argparse.ArgumentParser()
    argumentos.add_argument("--carga", type=int)
    argumentos.add_argument("--caminho", choices=("lote", "cdc"))
    a = argumentos.parse_args()
    ok = reconciliar(ConfigLakehouse.do_ambiente(), a.carga, (a.caminho,) if a.caminho else ("lote", "cdc"))
    if not ok:
        log.error("divergência entre a origem e o lakehouse")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
