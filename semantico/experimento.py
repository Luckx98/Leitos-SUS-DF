"""Grava o vetor da frase do mart e compara o cosseno com `acima_de_85`.

O modelo é o paraphrase-multilingual-MiniLM-L12-v2, 384 dimensões, já na imagem.
Não há chave de API. A amostra não baixa o modelo de novo (`MODELO_OFFLINE=1`).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

import psycopg

from semantico.frases import PERGUNTAS, TOPO, chave, frase, resumir
from transformacao.caminhos import pasta_medicoes

log = logging.getLogger("semantico")

MODELO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DIMENSAO = 384

CONSULTA_MART = """
SELECT o.cod_regiao_saude,
       r.nome AS nome_regiao,
       o.semana,
       o.ano,
       o.ocupacao,
       o.acima_de_85,
       o.leitos_sus,
       o.paciente_dias,
       c.capitulo_cid,
       c.capitulo_nome,
       c.parcela
FROM consumo.ocupacao_semana_regiao o
JOIN consumo.dim_regiao_saude r USING (cod_regiao_saude)
LEFT JOIN LATERAL (
    SELECT capitulo_cid, capitulo_nome, parcela
    FROM consumo.causa_semana_regiao
    WHERE cod_regiao_saude = o.cod_regiao_saude
      AND semana = o.semana
    ORDER BY paciente_dias DESC
    LIMIT 1
) c ON true
ORDER BY o.semana, o.cod_regiao_saude
"""


def carregar_modelo():
    from fastembed import TextEmbedding

    cache = os.environ.get("FASTEMBED_CACHE_PATH", "/app/modelos")
    offline = os.environ.get("MODELO_OFFLINE", "1") == "1"
    modelo = TextEmbedding(model_name=MODELO, cache_dir=cache, local_files_only=offline)
    if modelo.embedding_size != DIMENSAO:
        raise RuntimeError(f"dimensão {modelo.embedding_size}, a tabela espera {DIMENSAO}")
    return modelo


def _vetor(modelo, texto: str) -> list[float]:
    vetor = next(iter(modelo.embed([texto])))
    return [float(item) for item in vetor]


def _literal(vetor: list[float]) -> str:
    return "[" + ",".join(f"{item:.8f}" for item in vetor) + "]"


def _linhas(pg: psycopg.Connection) -> list[dict]:
    cursor = pg.execute(CONSULTA_MART)
    colunas = [item.name for item in cursor.description]
    return [dict(zip(colunas, linha)) for linha in cursor.fetchall()]


def _gravar(pg: psycopg.Connection, modelo, linhas: list[dict]) -> int:
    pg.execute("TRUNCATE semantico.trecho")
    textos = [frase(linha) for linha in linhas]
    vetores = list(modelo.embed(textos, batch_size=64))
    registros = []
    for linha, texto, vetor in zip(linhas, textos, vetores):
        valores = [float(item) for item in vetor]
        if len(valores) != DIMENSAO:
            raise RuntimeError(f"vetor com {len(valores)} dimensões")
        registros.append(
            (
                str(linha["cod_regiao_saude"]),
                linha["nome_regiao"],
                linha["semana"],
                int(linha["ano"]),
                float(linha["ocupacao"]),
                bool(linha["acima_de_85"]),
                linha["capitulo_cid"],
                linha["capitulo_nome"],
                texto,
                _literal(valores),
            )
        )
    with pg.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO semantico.trecho (
                cod_regiao_saude, nome_regiao, semana, ano, ocupacao, acima_de_85,
                capitulo_cid, capitulo_nome, texto, embedding
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
            """,
            registros,
        )
    pg.execute("DROP INDEX IF EXISTS semantico.trecho_embedding_hnsw")
    pg.execute(
        """
        CREATE INDEX trecho_embedding_hnsw
            ON semantico.trecho
            USING hnsw (embedding vector_cosine_ops)
        """
    )
    pg.execute("ANALYZE semantico.trecho")
    return len(registros)


def _topo(pg: psycopg.Connection, vetor: list[float]) -> tuple[list[dict], str]:
    literal = _literal(vetor)
    consulta = f"""
        SELECT cod_regiao_saude, nome_regiao, semana, ano, ocupacao, acima_de_85,
               capitulo_nome, 1 - (embedding <=> '{literal}'::vector) AS cosseno
        FROM semantico.trecho
        ORDER BY embedding <=> '{literal}'::vector
        LIMIT {TOPO}
    """
    cursor = pg.execute(consulta)
    colunas = [item.name for item in cursor.description]
    linhas = [dict(zip(colunas, linha)) for linha in cursor.fetchall()]
    plano = "\n".join(
        linha[0] for linha in pg.execute("EXPLAIN (ANALYZE, BUFFERS) " + consulta).fetchall()
    )
    return linhas, plano


def _acima(pg: psycopg.Connection) -> set[tuple[str, str]]:
    linhas = pg.execute(
        """
        SELECT cod_regiao_saude, semana
        FROM consumo.ocupacao_semana_regiao
        WHERE acima_de_85
        """
    ).fetchall()
    return {chave(cod, semana) for cod, semana in linhas}


def _formatar_topo(linhas: list[dict]) -> list[str]:
    saida = []
    for ordem, linha in enumerate(linhas, start=1):
        marca = "acima de 85%" if linha["acima_de_85"] else "abaixo de 85%"
        saida.append(
            f"{ordem}. {linha['nome_regiao']} {linha['semana']}  "
            f"cosseno={float(linha['cosseno']):.3f}  "
            f"ocupação={float(linha['ocupacao']):.1%}  {marca}  "
            f"causa={linha['capitulo_nome'] or 'sem causa'}"
        )
    return saida


def executar() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    modelo = carregar_modelo()
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as pg:
        linhas = _linhas(pg)
        if not linhas:
            raise RuntimeError("consumo.ocupacao_semana_regiao está vazio")
        total = _gravar(pg, modelo, linhas)
        acima = _acima(pg)
        log.info("%s trechos, %s semanas acima de 85%%", total, len(acima))

        blocos = [
            f"# Busca vetorial × limiar de 85% — {datetime.now():%Y-%m-%d %H:%M}",
            f"modelo={MODELO}  dimensões={DIMENSAO}  trechos={total}  "
            f"semanas acima de 85%={len(acima)}  top-k={TOPO}",
            "",
            "O vetor é da frase do mart. O cosseno ordena vizinhos de texto.",
            "O limiar `acima_de_85` continua sendo a coluna do warehouse.",
            "",
        ]
        for pergunta in PERGUNTAS:
            topo, plano = _topo(pg, _vetor(modelo, pergunta))
            conta = resumir(topo, acima)
            blocos.append(f"## {pergunta}")
            blocos.extend(_formatar_topo(topo))
            blocos.append(
                f"no topo e acima de 85%: {conta['no_topo_e_acima']} de {conta['no_topo']}; "
                f"no topo e abaixo de 85%: {conta['no_topo_abaixo']}; "
                f"acima de 85% fora do topo: {conta['acima_fora_do_topo']} "
                f"de {conta['acima_no_total']}"
            )
            blocos.append("plano:")
            blocos.append(plano)
            blocos.append("")

    caminho = pasta_medicoes() / f"vetor_{datetime.now():%Y-%m-%d}.txt"
    caminho.write_text("\n".join(blocos) + "\n", encoding="utf-8")
    log.info("comparação em %s", caminho)
    print("\n".join(blocos))
