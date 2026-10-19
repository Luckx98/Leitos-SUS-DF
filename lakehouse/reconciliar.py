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

import psycopg
import pyarrow.compute as pc

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


def ler_iceberg(catalogo, namespace: str, tabela: str, carga: int | None):
    coluna = COLUNA_CARGA[tabela]
    iceberg = catalogo.load_table(f"{namespace}.{tabela}")
    if iceberg.current_snapshot() is None:
        return None
    campos = tuple(dict.fromkeys((coluna, *CHAVES[tabela], "_commit_em", "_ingerido_em")))
    varredura = iceberg.scan(selected_fields=campos, **({"row_filter": f"{coluna} == {carga}"} if carga else {}))
    return varredura.to_arrow()


def reconciliar(config: ConfigLakehouse, carga: int | None = None,
                caminhos: tuple[str, ...] = ("lote", "cdc")) -> bool:
    catalogo = abrir_catalogo(config)
    ok = True
    with psycopg.connect(config.database_url) as conexao:
        for tabela in TABELAS:
            origem = contar_origem(conexao, tabela, carga)
            total_origem = sum(origem.values())
            partes = [f"{tabela:<23} origem {total_origem:>9}"]
            for namespace in caminhos:
                dados = ler_iceberg(catalogo, namespace, tabela, carga)
                if dados is None or dados.num_rows == 0:
                    partes.append(f"{namespace} {0:>9}")
                    ok &= total_origem == 0
                    continue
                contagem = Counter(dados[COLUNA_CARGA[tabela]].to_pylist())
                chaves = set(zip(*(dados[c].to_pylist() for c in CHAVES[tabela])))
                duplicatas = dados.num_rows - len(chaves)
                latencia = pc.subtract(dados["_ingerido_em"], dados["_commit_em"]).cast("int64")
                media_s = pc.mean(latencia).as_py() / 1e6 if dados.num_rows else 0
                igual = contagem == origem and duplicatas == 0
                ok &= igual
                partes.append(f"{namespace} {dados.num_rows:>9} dup {duplicatas:>5} lat.média {media_s:>8.1f}s "
                              f"{'ok' if igual else 'DIVERGE'}")
            log.info(" | ".join(partes))
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
