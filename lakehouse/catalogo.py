"""Acesso ao catálogo Iceberg (SQL catalog no PostgreSQL) e ao armazenamento S3."""

from __future__ import annotations

from pyarrow import fs
from pyiceberg.catalog.sql import SqlCatalog

from lakehouse.config import BUCKET_LAKEHOUSE, ConfigLakehouse


def abrir_catalogo(config: ConfigLakehouse) -> SqlCatalog:
    """O catálogo guarda só os ponteiros para os metadados; os dados ficam no S3."""
    return SqlCatalog(
        "leitos",
        uri=config.catalogo_url,
        warehouse=f"s3://{BUCKET_LAKEHOUSE}",
        **config.propriedades_s3(),
    )


def sistema_de_arquivos(config: ConfigLakehouse) -> fs.S3FileSystem:
    endpoint = config.s3_endpoint.removeprefix("http://").removeprefix("https://")
    return fs.S3FileSystem(
        endpoint_override=endpoint,
        scheme="https" if config.s3_endpoint.startswith("https") else "http",
        access_key=config.s3_access_key,
        secret_key=config.s3_secret_key,
        region="us-east-1",
        force_virtual_addressing=False,
        allow_bucket_creation=True,
    )
