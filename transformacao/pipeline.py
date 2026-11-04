"""Orquestra o dbt e devolve o tempo da construção, para a medição da opção nula."""

from __future__ import annotations

import json
import logging
import subprocess
import time

from transformacao.caminhos import PROJETO_DBT, serie_completa as serie_do_ambiente
from transformacao.fontes import registrar

log = logging.getLogger("transformacao.pipeline")

ULTIMO_BUILD_S: float = 0.0


def construir(anos: list[int] | None = None, serie_completa: bool | None = None) -> float:
    """Roda `dbt build`. Devolve os segundos. `anos` restringe só os marts."""
    global ULTIMO_BUILD_S
    registrar()
    serie = serie_do_ambiente() if serie_completa is None else serie_completa
    variaveis = {"anos": anos or [], "serie_completa": serie}
    comando = [
        "dbt", "build",
        "--project-dir", str(PROJETO_DBT),
        "--profiles-dir", str(PROJETO_DBT),
        "--vars", json.dumps(variaveis),
    ]
    log.info("dbt build vars=%s", variaveis)
    inicio = time.perf_counter()
    subprocess.run(comando, check=True)
    ULTIMO_BUILD_S = time.perf_counter() - inicio
    log.info("dbt build em %.1f s", ULTIMO_BUILD_S)
    return ULTIMO_BUILD_S


def executar() -> None:
    from transformacao.explicar import explicar
    from transformacao.medir import medir
    from transformacao.publicar import publicar

    segundos = construir()
    publicar()
    explicar()
    medir(segundos_dbt=segundos)
