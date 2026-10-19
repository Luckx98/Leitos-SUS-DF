"""Prepara o lakehouse: banco do catálogo, buckets, namespaces e tabelas Iceberg.

Idempotente: pode rodar a cada `docker compose --profile e2 up`.
    python -m lakehouse.preparar
"""

from __future__ import annotations

import logging
import sys
import time

import psycopg
from pyarrow import fs
from sqlalchemy.engine import make_url

from lakehouse.catalogo import abrir_catalogo, sistema_de_arquivos
from lakehouse.config import BUCKET_BRUTO, BUCKET_LAKEHOUSE, ConfigLakehouse
from lakehouse.esquemas import NAMESPACES, TABELAS, definicao

log = logging.getLogger("lakehouse")


def criar_banco_do_catalogo(config: ConfigLakehouse) -> None:
    """O catálogo fica num banco separado da origem, no mesmo servidor."""
    nome = make_url(config.catalogo_url).database
    with psycopg.connect(config.database_url, autocommit=True) as conexao:
        existe = conexao.execute("SELECT 1 FROM pg_database WHERE datname = %s", (nome,)).fetchone()
        if not existe:
            conexao.execute(f'CREATE DATABASE "{nome}"')
            log.info("banco do catálogo %s criado", nome)


def criar_buckets(config: ConfigLakehouse, tentativas: int = 20) -> None:
    s3 = sistema_de_arquivos(config)
    for bucket in (BUCKET_LAKEHOUSE, BUCKET_BRUTO):
        for tentativa in range(1, tentativas + 1):
            try:
                if s3.get_file_info(bucket).type == fs.FileType.NotFound:
                    s3.create_dir(bucket)
                    log.info("bucket %s criado", bucket)
                break
            except OSError as erro:
                # O S3 do SeaweedFS fica pronto alguns segundos depois do master.
                if tentativa == tentativas:
                    raise
                log.info("S3 ainda não respondeu (%s); nova tentativa", erro)
                time.sleep(2)


def criar_tabelas(config: ConfigLakehouse) -> None:
    catalogo = abrir_catalogo(config)
    for namespace in NAMESPACES:
        catalogo.create_namespace_if_not_exists(namespace)
        for nome in TABELAS:
            d = definicao(nome)
            catalogo.create_table_if_not_exists(
                f"{namespace}.{nome}",
                schema=d.schema,
                partition_spec=d.particao,
                properties={
                    "write.parquet.compression-codec": "zstd",
                    "format-version": "2",
                },
            )
    log.info("tabelas: %s", ", ".join(f"{n}.{t}" for n in NAMESPACES for t in TABELAS))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = ConfigLakehouse.do_ambiente()
    criar_banco_do_catalogo(config)
    criar_buckets(config)
    criar_tabelas(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
