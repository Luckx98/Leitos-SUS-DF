"""Camada bruta: copia os arquivos originais do DATASUS para o bucket `bruto`.

O nome do objeto leva o início do sha256 do conteúdo:
    bruto/<fonte>/<sha256[:16]>_<arquivo original>
Assim o bruto é imutável: se o DATASUS republicar um arquivo com o mesmo nome e
outro conteúdo, os dois ficam guardados. Enviar de novo um arquivo que já está
no bucket não faz nada.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from pyarrow import fs

from lakehouse.catalogo import sistema_de_arquivos
from lakehouse.config import BUCKET_BRUTO, ConfigLakehouse
from loader.ftp import sha256

log = logging.getLogger("lakehouse.brutos")

PREFIXOS = {"RD": "SIH_RD", "ST": "CNES_ST", "LT": "CNES_LT"}


def fonte_do_arquivo(caminho: Path) -> str:
    if caminho.name.upper().startswith("TAB_SIH"):
        return "REFERENCIA"
    return PREFIXOS.get(caminho.name[:2].upper(), "OUTROS")


def chave(caminho: Path, hash_arquivo: str) -> str:
    return f"{BUCKET_BRUTO}/{fonte_do_arquivo(caminho)}/{hash_arquivo[:16]}_{caminho.name}"


def arquivos_locais(diretorios: list[Path]) -> list[Path]:
    encontrados = []
    for diretorio in diretorios:
        if diretorio.is_dir():
            encontrados += [p for p in diretorio.rglob("*") if p.suffix.lower() in {".dbc", ".zip"} and p.is_file()]
    return sorted(encontrados)


def enviar_brutos(config: ConfigLakehouse) -> tuple[int, int]:
    """Envia o que ainda não está no bucket. Devolve (arquivos enviados, bytes enviados)."""
    diretorios = [Path(d) for d in os.environ.get("DIRS_BRUTOS", "/dados/brutos:/app/dados/amostra").split(":")]
    s3 = sistema_de_arquivos(config)
    enviados = bytes_enviados = existentes = 0
    for caminho in arquivos_locais(diretorios):
        destino = chave(caminho, sha256(caminho))
        if s3.get_file_info(destino).type != fs.FileType.NotFound:
            existentes += 1
            continue
        with caminho.open("rb") as origem, s3.open_output_stream(destino) as saida:
            while bloco := origem.read(8 * 1024 * 1024):
                saida.write(bloco)
        enviados += 1
        bytes_enviados += caminho.stat().st_size
    log.info("bruto: %d arquivo(s) enviados (%.1f MB), %d já estavam no bucket",
             enviados, bytes_enviados / 1e6, existentes)
    return enviados, bytes_enviados
