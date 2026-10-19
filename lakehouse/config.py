"""Conexões do lakehouse, lidas de variáveis de ambiente."""

from __future__ import annotations

import os
from dataclasses import dataclass

BUCKET_LAKEHOUSE = "lakehouse"
BUCKET_BRUTO = "bruto"


@dataclass(frozen=True)
class ConfigLakehouse:
    database_url: str
    catalogo_url: str
    s3_endpoint: str
    s3_access_key: str
    s3_secret_key: str

    @classmethod
    def do_ambiente(cls) -> ConfigLakehouse:
        return cls(
            database_url=os.environ["DATABASE_URL"],
            catalogo_url=os.environ["CATALOGO_URL"],
            s3_endpoint=os.environ.get("S3_ENDPOINT", "http://seaweedfs:8333"),
            s3_access_key=os.environ.get("S3_ACCESS_KEY", "leitos"),
            s3_secret_key=os.environ.get("S3_SECRET_KEY", "leitos-segredo"),
        )

    def propriedades_s3(self) -> dict[str, str]:
        """Propriedades do FileIO do pyiceberg para um S3 que não é a AWS."""
        return {
            "s3.endpoint": self.s3_endpoint,
            "s3.access-key-id": self.s3_access_key,
            "s3.secret-access-key": self.s3_secret_key,
            "s3.region": "us-east-1",
            "s3.force-virtual-addressing": "false",
        }
