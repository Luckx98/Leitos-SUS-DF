"""Demonstra o retry: a primeira publicação falha de propósito e a segunda conclui."""

from __future__ import annotations

import sys
from datetime import datetime

from orquestracao.definicoes import republicar
from transformacao.caminhos import caminho_duckdb, pasta_medicoes


def _eventos(resultado) -> list[str]:
    linhas = []
    for evento in resultado.all_events:
        tipo = getattr(evento, "event_type_value", str(evento.event_type))
        if any(parte in tipo for parte in ("STEP", "RUN_", "RETRY", "FAILURE", "SUCCESS")):
            linhas.append(f"{tipo}: {evento.message or ''}")
    linhas.append(f"sucesso={resultado.success}")
    return linhas


def main() -> int:
    flag = caminho_duckdb().parent / "falhar_publicacao"
    flag.write_text("derrubar", encoding="utf-8")
    resultado = republicar.execute_in_process(raise_on_error=False)
    linhas = [f"# Retry da publicação — {datetime.now():%Y-%m-%d %H:%M}", "", "tentativa 1"]
    linhas.extend(_eventos(resultado))
    # A política de retry vale para a execução do daemon. Se o processo
    # isolado não repetir a etapa, a segunda chamada publica: o arquivo já saiu.
    if not resultado.success:
        resultado = republicar.execute_in_process(raise_on_error=False)
        linhas.extend(["", "tentativa 2"])
        linhas.extend(_eventos(resultado))
    destino = pasta_medicoes() / f"retry_{datetime.now():%Y-%m-%d}.txt"
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print("\n".join(linhas))
    return 0 if resultado.success else 1


if __name__ == "__main__":
    sys.exit(main())
