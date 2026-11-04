"""Caminhos do projeto, dentro e fora do container."""

from __future__ import annotations

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PROJETO_DBT = RAIZ / "transformacao"


def caminho_duckdb() -> Path:
    bruto = os.environ.get("DUCKDB_PATH", str(RAIZ / "var" / "analitico.duckdb"))
    caminho = Path(bruto)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    return caminho


def pasta_medicoes() -> Path:
    pasta = RAIZ / "medicoes" / "e3"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def serie_completa() -> bool:
    """A série 2021–2025 só é exigida na carga completa, e pode ser desligada."""
    bruto = os.environ.get("SERIE_COMPLETA", "").strip().lower()
    if bruto in {"1", "true", "sim", "yes"}:
        return True
    if bruto in {"0", "false", "nao", "não", "no"}:
        return False
    return os.environ.get("MODO", "amostra") == "completo"


def host_s3() -> str:
    endpoint = os.environ.get("S3_ENDPOINT", "http://seaweedfs:8333")
    return endpoint.removeprefix("https://").removeprefix("http://").rstrip("/")
