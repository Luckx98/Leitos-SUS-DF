"""Sobe a camada analítica uma vez: fontes, dbt, publicação, planos e medição.

    python -m transformacao
"""

from __future__ import annotations

import logging
import sys

from transformacao.pipeline import executar


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    executar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
