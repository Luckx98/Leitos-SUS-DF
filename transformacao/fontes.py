"""Registra o snapshot atual de lote.* e as tabelas de referência para o dbt.

O catálogo Iceberg é SQL. O DuckDB lê cada tabela pelo metadata_location do
snapshot corrente (iceberg_scan), com o S3 do SeaweedFS. As referências
(CID, município, região e a tabela curada do DF) não foram para o lakehouse
na E2: são copiadas do Postgres para o schema espelho.
"""

from __future__ import annotations

import logging
import os

import duckdb
import pyarrow as pa

from lakehouse.catalogo import abrir_catalogo
from lakehouse.config import ConfigLakehouse
from transformacao.caminhos import caminho_duckdb, host_s3

log = logging.getLogger("transformacao.fontes")

TABELAS_LOTE = ("carga", "estabelecimento_versao", "leito", "internacao", "maturidade")
TABELAS_ORIGEM = ("municipio", "cid", "regiao_saude", "estabelecimento_regiao_df")


def _carregar(con: duckdb.DuckDBPyConnection, nome: str) -> None:
    try:
        con.execute(f"LOAD {nome}")
    except duckdb.Error:
        con.execute(f"INSTALL {nome}")
        con.execute(f"LOAD {nome}")


def configurar_s3(con: duckdb.DuckDBPyConnection) -> None:
    _carregar(con, "httpfs")
    _carregar(con, "iceberg")
    os.environ["S3_HOST"] = host_s3()
    con.execute(f"SET s3_endpoint='{host_s3()}'")
    con.execute(f"SET s3_access_key_id='{os.environ.get('S3_ACCESS_KEY', 'leitos')}'")
    con.execute(f"SET s3_secret_access_key='{os.environ.get('S3_SECRET_KEY', 'leitos-segredo')}'")
    con.execute("SET s3_use_ssl=false")
    con.execute("SET s3_url_style='path'")
    con.execute("SET s3_region='us-east-1'")


def _literal(valor: str) -> str:
    return "'" + valor.replace("'", "''") + "'"


def _tabela_vazia(con: duckdb.DuckDBPyConnection, nome: str, esquema: pa.Schema) -> None:
    vazio = pa.table({campo.name: pa.array([], type=campo.type) for campo in esquema})
    con.register(f"vazio_{nome}", vazio)
    con.execute(f"CREATE OR REPLACE TABLE espelho.{nome} AS SELECT * FROM vazio_{nome}")
    con.unregister(f"vazio_{nome}")


def registrar() -> None:
    config = ConfigLakehouse.do_ambiente()
    catalogo = abrir_catalogo(config)
    con = duckdb.connect(str(caminho_duckdb()))
    configurar_s3(con)
    con.execute("CREATE SCHEMA IF NOT EXISTS espelho")
    for nome in TABELAS_LOTE:
        tabela = catalogo.load_table(f"lote.{nome}")
        if tabela.current_snapshot() is None:
            log.info("lote.%s sem snapshot; espelho.%s fica vazia", nome, nome)
            _tabela_vazia(con, nome, tabela.schema().as_arrow())
            continue
        local = tabela.metadata_location
        con.execute(
            f"CREATE OR REPLACE VIEW espelho.{nome} AS SELECT * FROM iceberg_scan({_literal(local)})"
        )
        linhas = con.execute(f"SELECT count(*) FROM espelho.{nome}").fetchone()[0]
        log.info("espelho.%-24s %10d linhas  %s", nome, linhas, local)

    _carregar(con, "postgres")
    con.execute(f"ATTACH {_literal(config.database_url)} AS origem (TYPE postgres, READ_ONLY)")
    for nome in TABELAS_ORIGEM:
        con.execute(f"CREATE OR REPLACE TABLE espelho.{nome} AS SELECT * FROM origem.public.{nome}")
        linhas = con.execute(f"SELECT count(*) FROM espelho.{nome}").fetchone()[0]
        log.info("espelho.%-24s %10d linhas  (origem)", nome, linhas)
    con.execute("DETACH origem")
    con.close()


def conferir_lote() -> None:
    """O grafo só segue se o caminho de lote já gravou internações."""
    config = ConfigLakehouse.do_ambiente()
    tabela = abrir_catalogo(config).load_table("lote.internacao")
    if tabela.current_snapshot() is None:
        raise RuntimeError("lote.internacao não tem snapshot; o lote precisa rodar antes da transformação")
