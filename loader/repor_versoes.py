"""Regrava versões do CNES anteriores à amostra.

A carga completa ignora um arquivo cujo sha256 já está em `carga`. A amostra de
01/2025 tinha entrado antes, e o loader descartava o cadastro de 2021–2024
porque já existia uma versão posterior. Este comando relê os ST em
`DIR_BRUTOS` em ordem cronológica e insere só as versões que faltam, numa
carga nova, para o lote enxergar o id.

    python -m loader.repor_versoes
"""

from __future__ import annotations

import hashlib
import logging
import sys
from datetime import datetime, timezone

import psycopg

from loader.carga import Arquivo
from loader.cnes import processar_st
from loader.config import Config
from loader.__main__ import _interpretar, _ordenar

log = logging.getLogger("loader.repor_versoes")


def arquivos_st(config: Config) -> list[Arquivo]:
    diretorio = config.dir_brutos / "CNES_ST"
    encontrados = [arquivo for caminho in sorted(diretorio.glob("ST*.dbc")) if (arquivo := _interpretar(caminho))]
    return [arquivo for arquivo in _ordenar(encontrados) if arquivo.uf in config.ufs]


def repor(conexao: psycopg.Connection, arquivos: list[Arquivo]) -> int:
    """Insere as versões que faltam. Devolve quantas linhas novas gravou."""
    if not arquivos:
        log.error("nenhum ST em %s", "DIR_BRUTOS/CNES_ST")
        return 0

    lidas = rejeitadas = inseridas = 0
    with conexao.transaction():
        id_carga = conexao.execute("SELECT nextval(pg_get_serial_sequence('carga', 'id_carga'))").fetchone()[0]
        iniciada_em = datetime.now(timezone.utc)
        for arquivo in arquivos:
            resultado, novas = processar_st(conexao, id_carga, arquivo)
            lidas += resultado.linhas_lidas
            rejeitadas += len(resultado.rejeicoes)
            inseridas += novas
            log.info("%s: %d versões novas", arquivo.caminho.name, novas)
        if inseridas == 0:
            raise psycopg.Rollback()
        digest = hashlib.sha256(f"repor-versoes-{iniciada_em.isoformat()}".encode()).hexdigest()
        conexao.execute(
            """
            INSERT INTO carga (id_carga, fonte, arquivo, sha256, tamanho_bytes, iniciada_em,
                               linhas_lidas, linhas_inseridas, linhas_rejeitadas, status, mensagem)
            OVERRIDING SYSTEM VALUE
            VALUES (%s, 'CNES_ST', 'repor-versoes-anteriores', %s, 0, %s, %s, %s, %s, 'concluida', %s)
            """,
            (
                id_carga,
                digest,
                iniciada_em,
                lidas,
                inseridas,
                rejeitadas,
                "versões de cadastro anteriores à amostra, relidas dos ST já baixados",
            ),
        )
    log.info("carga %s: %d linhas novas", id_carga, inseridas)
    return inseridas


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = Config.do_ambiente()
    arquivos = arquivos_st(config)
    log.info("%d arquivos ST", len(arquivos))
    with psycopg.connect(config.database_url, autocommit=True) as conexao:
        inseridas = repor(conexao, arquivos)
    if not arquivos:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
