#!/usr/bin/env bash
# Compacta cdc.* com o consumidor parado (ele escreve a cada poucos segundos e
# entraria em conflito com a compactação). lote.* é compactado no fim de todo lote.
#
# Uso: scripts/compactar_cdc.sh
set -euo pipefail
DC="docker compose --profile e2"
$DC stop cdc >/dev/null 2>&1
trap '$DC start cdc >/dev/null 2>&1' EXIT
$DC run --rm --no-deps lote python -m lakehouse.compactar --namespace cdc
