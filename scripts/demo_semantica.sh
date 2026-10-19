#!/usr/bin/env bash
# Demonstração da semântica de entrega (lote e CDC).
#
# Uso (com o perfil e2 no ar e o cdc.* já reconciliado):
#   scripts/demo_semantica.sh
#
# O serviço cdc é parado durante a demonstração, que roda o consumidor em
# primeiro plano, e é religado no fim.
set -euo pipefail

DC="docker compose --profile e2"

$DC stop cdc >/dev/null 2>&1
trap '$DC start cdc >/dev/null 2>&1' EXIT
$DC run --rm --no-deps cdc python -m lakehouse.demo_semantica
