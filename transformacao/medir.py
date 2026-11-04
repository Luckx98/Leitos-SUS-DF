"""Mede os dois grãos e a opção nula (SQL direto na origem, o que um cron rodaria)."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from pathlib import Path

import duckdb
import psycopg

from transformacao.caminhos import RAIZ, caminho_duckdb, pasta_medicoes
from transformacao.fontes import configurar_s3

log = logging.getLogger("transformacao.medir")

CONSULTA_NULA = (RAIZ / "sql" / "e3" / "opcao_nula.sql").read_text(encoding="utf-8")


def _tempo_origem() -> tuple[float, int, int]:
    inicio = time.perf_counter()
    with psycopg.connect(os.environ["DATABASE_URL"]) as pg:
        linhas = pg.execute(CONSULTA_NULA).fetchall()
    segundos = time.perf_counter() - inicio
    acima = sum(1 for linha in linhas if linha[-1] is not None and float(linha[-1]) > 0.85)
    return segundos, len(linhas), acima


def _tempo_consumo() -> tuple[float, int]:
    inicio = time.perf_counter()
    with psycopg.connect(os.environ["DATABASE_URL"]) as pg:
        total = pg.execute(
            "SELECT count(*) FROM consumo.ocupacao_semana_regiao WHERE acima_de_85"
        ).fetchone()[0]
    return time.perf_counter() - inicio, total


def medir(segundos_dbt: float) -> Path:
    segundos_nula, linhas_nula, acima_nula = _tempo_origem()
    segundos_consumo, acima_consumo = _tempo_consumo()

    con = duckdb.connect(str(caminho_duckdb()))
    configurar_s3(con)
    internacoes = con.execute("SELECT count(*) FROM marts.fato_internacao").fetchone()[0]
    semanas = con.execute("SELECT count(*) FROM marts.ocupacao_semana_regiao").fetchone()[0]
    causas = con.execute("SELECT count(*) FROM marts.causa_semana_regiao").fetchone()[0]

    inicio = time.perf_counter()
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE paciente_dia AS
        SELECT cod_regiao_saude, semana, capitulo_cid FROM intermediate.int_paciente_dia
        """
    )
    segundos_persistir = time.perf_counter() - inicio
    paciente_dias = con.execute("SELECT count(*) FROM paciente_dia").fetchone()[0]
    inicio = time.perf_counter()
    con.execute(
        "SELECT cod_regiao_saude, semana, count(*) FROM paciente_dia GROUP BY 1, 2"
    ).fetchall()
    segundos_fino = time.perf_counter() - inicio
    inicio = time.perf_counter()
    con.execute(
        """
        SELECT cod_regiao_saude, semana, paciente_dias
        FROM marts.ocupacao_semana_regiao
        """
    ).fetchall()
    segundos_grosso = time.perf_counter() - inicio
    pasta = Path("/tmp/e3-graos")
    pasta.mkdir(exist_ok=True)
    fino = pasta / "paciente_dia.parquet"
    grosso = pasta / "ocupacao.parquet"
    con.execute(f"COPY paciente_dia TO '{fino}' (FORMAT parquet, COMPRESSION zstd)")
    con.execute(f"COPY marts.ocupacao_semana_regiao TO '{grosso}' (FORMAT parquet, COMPRESSION zstd)")
    con.close()

    caminho = pasta_medicoes() / f"granularidade_{datetime.now():%Y-%m-%d}.txt"
    caminho.write_text(
        "\n".join([
            f"# Grãos e opção nula — {datetime.now():%Y-%m-%d %H:%M}",
            f"# modo={os.environ.get('MODO', 'amostra')}",
            "",
            "## Volume",
            f"internações (fato_internacao)          {internacoes}",
            f"paciente-dia (grão fino, não persistido no consumo)  {paciente_dias}",
            f"ocupação semana × região (grão grosso) {semanas}",
            f"causa semana × região × capítulo       {causas}",
            f"parquet do paciente-dia                {fino.stat().st_size / 1e6:.2f} MB",
            f"parquet da ocupação semanal            {grosso.stat().st_size / 1e6:.2f} MB",
            "",
            "## Tempo da pergunta (semanas e a contagem de paciente-dia)",
            f"agregar o grão fino já materializado   {segundos_fino * 1000:.1f} ms",
            f"ler o grão grosso                      {segundos_grosso * 1000:.1f} ms",
            f"persistir o grão fino (custo de guardá-lo) {segundos_persistir:.1f} s",
            f"ler o consumo no Postgres (acima de 85%)   {segundos_consumo * 1000:.1f} ms  ({acima_consumo} semanas)",
            "",
            "## Opção nula: SQL da L4 direto na origem, sem modelo nem teste",
            f"tempo                                  {segundos_nula:.1f} s",
            f"linhas (região × semana)               {linhas_nula}",
            f"semanas com ocupação acima de 85%      {acima_nula}",
            f"dbt build (modelo, testes e as duas camadas) {segundos_dbt:.1f} s",
            "",
            "O grão fino não entra no schema consumo: a pergunta lê o grão grosso.",
            "Na carga completa de um ano a mesma expansão, feita na origem a cada consulta, levou 6,4 s (E1, L4).",
            "",
        ]),
        encoding="utf-8",
    )
    log.info("medição em %s", caminho)
    return caminho
