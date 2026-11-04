"""Backfill por ano: esvazia o consumo, preenche cada ano presente e recria os índices."""

from __future__ import annotations

import os
import sys
from datetime import datetime

import duckdb
import psycopg
from dagster import materialize

from orquestracao.definicoes import consumo_ano
from transformacao.caminhos import caminho_duckdb, pasta_medicoes
from transformacao.explicar import explicar
from transformacao.fontes import configurar_s3
from transformacao.pipeline import construir
from transformacao.publicar import publicar


def _contar() -> tuple[int, int]:
    with psycopg.connect(os.environ["DATABASE_URL"]) as pg:
        total, anos = pg.execute(
            "SELECT count(*), count(DISTINCT ano) FROM consumo.ocupacao_semana_regiao"
        ).fetchone()
    return int(total), int(anos)


def _anos_presentes() -> list[int]:
    try:
        con = duckdb.connect(str(caminho_duckdb()), read_only=True)
    except duckdb.IOException:
        con = duckdb.connect(str(caminho_duckdb()))
    configurar_s3(con)
    anos = [
        int(linha[0])
        for linha in con.execute("SELECT DISTINCT ano FROM intermediate.int_semana ORDER BY 1").fetchall()
    ]
    con.close()
    return anos


def main() -> int:
    linhas = [f"# Backfill por ano — {datetime.now():%Y-%m-%d %H:%M}", ""]
    construir([2020], serie_completa=False)
    publicar([2020], substituir=True)
    total, distintos = _contar()
    linhas.append(f"depois de publicar só 2020 (ano sem competência nesta carga): {total} linhas, {distintos} anos")

    for ano in _anos_presentes():
        resultado = materialize([consumo_ano], partition_key=str(ano), raise_on_error=False)
        total, distintos = _contar()
        linhas.append(
            f"backfill {ano}: sucesso={resultado.success} → {total} linhas, {distintos} anos no consumo"
        )
        if not resultado.success:
            destino = pasta_medicoes() / f"backfill_{datetime.now():%Y-%m-%d}.txt"
            destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
            print("\n".join(linhas))
            return 1

    explicar()
    linhas.append("índices recriados e planos atualizados")
    destino = pasta_medicoes() / f"backfill_{datetime.now():%Y-%m-%d}.txt"
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print("\n".join(linhas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
