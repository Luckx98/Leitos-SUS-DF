"""Copia os marts do DuckDB para o schema Postgres `consumo`.

Substituição troca as tabelas inteiras. A publicação por ano apaga só as linhas
daqueles anos e insere de novo: é o que o backfill usa para não desfazer o
ano que já estava no consumo.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import duckdb
import psycopg

from transformacao.caminhos import caminho_duckdb
from transformacao.fontes import configurar_s3

log = logging.getLogger("transformacao.publicar")

DIMENSOES = (
    "dim_estabelecimento",
    "dim_semana",
    "dim_regiao_saude",
    "dim_cid",
    "sla",
)
FATOS = {
    "ocupacao_semana_regiao": "ano",
    "causa_semana_regiao": "ano",
    "fato_internacao": "extract(year from dt_saida)",
}


def _conectar_duckdb() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(caminho_duckdb()))
    configurar_s3(con)
    con.execute("LOAD postgres")
    return con


def publicar(anos: list[int] | None = None, substituir: bool = False) -> None:
    substituir = substituir or not anos
    url = os.environ["DATABASE_URL"]
    with psycopg.connect(url, autocommit=True) as pg:
        pg.execute("CREATE SCHEMA IF NOT EXISTS consumo")
    con = _conectar_duckdb()
    con.execute(f"ATTACH '{url}' AS pg (TYPE postgres)")
    for nome in DIMENSOES:
        _substituir(con, nome)
    for nome, coluna in FATOS.items():
        if substituir:
            _substituir(con, nome)
        else:
            _mesclar(con, url, nome, coluna, anos or [])
    _gravar_freshness(con, url)
    con.close()
    log.info("consumo publicado (%s)", "substituição" if substituir else f"anos {anos}")


def _substituir(con: duckdb.DuckDBPyConnection, nome: str) -> None:
    con.execute(f"DROP TABLE IF EXISTS pg.consumo.{nome}")
    con.execute(f"CREATE TABLE pg.consumo.{nome} AS SELECT * FROM marts.{nome}")
    linhas = con.execute(f"SELECT count(*) FROM marts.{nome}").fetchone()[0]
    log.info("consumo.%-28s %10d linhas", nome, linhas)


def _mesclar(con: duckdb.DuckDBPyConnection, url: str, nome: str, coluna: str, anos: list[int]) -> None:
    existe = con.execute(
        """
        SELECT count(*) FROM pg.information_schema.tables
        WHERE table_schema = 'consumo' AND table_name = ?
        """,
        [nome],
    ).fetchone()[0]
    if not existe:
        _substituir(con, nome)
        return
    with psycopg.connect(url, autocommit=True) as pg:
        pg.execute(f"DELETE FROM consumo.{nome} WHERE {coluna} = ANY(%s)", (anos,))
    con.execute(f"INSERT INTO pg.consumo.{nome} SELECT * FROM marts.{nome}")
    linhas = con.execute(f"SELECT count(*) FROM pg.consumo.{nome}").fetchone()[0]
    log.info("consumo.%-28s %10d linhas depois do ano %s", nome, linhas, anos)


def _gravar_freshness(con: duckdb.DuckDBPyConnection, url: str) -> None:
    linha = con.execute(
        """
        SELECT
            max(construida_em) AS construida,
            (SELECT max(_ingerido_em) FROM staging.stg_internacao) AS ingerido
        FROM marts.ocupacao_semana_regiao
        """
    ).fetchone()
    construida, ingerido = linha if linha else (None, None)
    agora = datetime.now(timezone.utc)
    if construida is None:
        atraso, dentro = None, False
    else:
        construida_utc = construida if construida.tzinfo else construida.replace(tzinfo=timezone.utc)
        atraso = (agora - construida_utc).total_seconds() / 3600
        ingerido_utc = None
        if ingerido is not None:
            ingerido_utc = ingerido if ingerido.tzinfo else ingerido.replace(tzinfo=timezone.utc)
        dentro = atraso <= 24 and (ingerido_utc is None or construida_utc >= ingerido_utc)
    with psycopg.connect(url, autocommit=True) as pg:
        pg.execute(
            """
            CREATE TABLE IF NOT EXISTS consumo.controle_freshness (
                tabela          TEXT PRIMARY KEY,
                construida_em   TIMESTAMPTZ,
                ingerido_em     TIMESTAMPTZ,
                atraso_horas    DOUBLE PRECISION,
                sla_horas       INTEGER NOT NULL,
                dentro_do_sla   BOOLEAN NOT NULL,
                medido_em       TIMESTAMPTZ NOT NULL
            )
            """
        )
        pg.execute(
            """
            INSERT INTO consumo.controle_freshness
                (tabela, construida_em, ingerido_em, atraso_horas, sla_horas, dentro_do_sla, medido_em)
            VALUES ('ocupacao_semana_regiao', %s, %s, %s, 24, %s, %s)
            ON CONFLICT (tabela) DO UPDATE SET
                construida_em = EXCLUDED.construida_em,
                ingerido_em = EXCLUDED.ingerido_em,
                atraso_horas = EXCLUDED.atraso_horas,
                sla_horas = EXCLUDED.sla_horas,
                dentro_do_sla = EXCLUDED.dentro_do_sla,
                medido_em = EXCLUDED.medido_em
            """,
            (construida, ingerido, atraso, dentro, agora),
        )
    log.info("freshness ocupacao_semana_regiao atraso=%s h dentro_do_sla=%s", atraso, dentro)


def ler_freshness() -> dict:
    with psycopg.connect(os.environ["DATABASE_URL"]) as pg:
        linha = pg.execute(
            """
            SELECT tabela, construida_em, ingerido_em, atraso_horas, sla_horas, dentro_do_sla
            FROM consumo.controle_freshness
            WHERE tabela = 'ocupacao_semana_regiao'
            """
        ).fetchone()
    if linha is None:
        raise RuntimeError("consumo.controle_freshness não tem a tabela de ocupação")
    return {
        "tabela": linha[0],
        "construida_em": linha[1],
        "ingerido_em": linha[2],
        "atraso_horas": linha[3],
        "sla_horas": linha[4],
        "dentro_do_sla": linha[5],
    }
