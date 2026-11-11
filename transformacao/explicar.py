"""Planos EXPLAIN (ANALYZE, BUFFERS) antes e depois dos índices.

A consulta da pergunta, no mart semanal, cabe em poucas mil linhas mesmo na
carga completa (uma linha por região por semana). O plano que muda de fato é
o de `fato_internacao`, filtrado por estabelecimento e data de saída: é o
acesso que a origem já indexava e que o mart precisa devolver sem varrer a AIH.
Os dois pares de plano ficam em medicoes/e3/. O da L4 na origem entra como
contexto: é a expansão de paciente-dia que esta camada materializa.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

import psycopg

from transformacao.caminhos import pasta_medicoes

log = logging.getLogger("transformacao.explicar")

DROP = """
DROP INDEX IF EXISTS consumo.idx_fato_internacao_cnes_saida;
DROP INDEX IF EXISTS consumo.idx_ocupacao_regiao_ano;
"""

INDICES = """
CREATE INDEX idx_fato_internacao_cnes_saida
    ON consumo.fato_internacao (cnes, dt_saida)
    INCLUDE (capitulo_cid, dias_permanencia);

CREATE INDEX idx_ocupacao_regiao_ano
    ON consumo.ocupacao_semana_regiao (cod_regiao_saude, ano, semana)
    INCLUDE (ocupacao, acima_de_85);
"""


def _plano(pg: psycopg.Connection, consulta: str) -> str:
    linhas = pg.execute("EXPLAIN (ANALYZE, BUFFERS) " + consulta).fetchall()
    return "\n".join(linha[0] for linha in linhas)


def _gravar(nome: str, consulta: str, plano: str) -> None:
    caminho = pasta_medicoes() / nome
    caminho.write_text(
        f"-- {datetime.now():%Y-%m-%d %H:%M}\n-- {consulta.strip()}\n\n{plano}\n",
        encoding="utf-8",
    )
    log.info("plano em %s", caminho)


def explicar() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as pg:
        pg.execute(DROP)
        pg.execute("ANALYZE consumo.fato_internacao")
        pg.execute("ANALYZE consumo.ocupacao_semana_regiao")

        cnes = pg.execute(
            """
            SELECT cnes FROM consumo.fato_internacao
            GROUP BY cnes ORDER BY count(*) DESC LIMIT 1
            """
        ).fetchone()
        regiao = pg.execute(
            """
            SELECT cod_regiao_saude, max(ano) FROM consumo.ocupacao_semana_regiao
            GROUP BY cod_regiao_saude ORDER BY count(*) DESC LIMIT 1
            """
        ).fetchone()
        if cnes is None or regiao is None:
            log.warning("consumo vazio; planos não gerados")
            return
        if not str(cnes[0]).isdigit() or not str(regiao[0]).isdigit():
            raise RuntimeError(f"chave inesperada: cnes={cnes[0]} regiao={regiao[0]}")

        fato = f"""
            SELECT capitulo_cid, count(*) AS internacoes, sum(dias_permanencia) AS paciente_dias
            FROM consumo.fato_internacao
            WHERE cnes = '{cnes[0]}'
              AND dt_saida >= DATE '2021-01-01' AND dt_saida < DATE '2026-01-01'
            GROUP BY capitulo_cid
            ORDER BY paciente_dias DESC
        """
        ocupacao = f"""
            SELECT semana, ocupacao, paciente_dias, leitos_sus
            FROM consumo.ocupacao_semana_regiao
            WHERE cod_regiao_saude = '{regiao[0]}' AND ano = {int(regiao[1])} AND ocupacao >= 0.85
            ORDER BY semana
        """
        _gravar("explain_fato_internacao_antes.txt", fato, _plano(pg, fato))
        _gravar("explain_ocupacao_antes.txt", ocupacao, _plano(pg, ocupacao))

        pg.execute(INDICES)
        pg.execute("ANALYZE consumo.fato_internacao")
        pg.execute("ANALYZE consumo.ocupacao_semana_regiao")
        _gravar("explain_fato_internacao_depois.txt", fato, _plano(pg, fato))
        _gravar("explain_ocupacao_depois.txt", ocupacao, _plano(pg, ocupacao))

        from transformacao.medir import CONSULTA_NULA
        _gravar("explain_l4_origem.txt", CONSULTA_NULA, _plano(pg, CONSULTA_NULA))
