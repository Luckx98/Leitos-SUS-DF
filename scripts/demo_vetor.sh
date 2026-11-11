#!/bin/sh
# Compara a busca por cosseno com o limiar de 85%. Exige o perfil e3 no ar.
set -eu
cd "$(dirname "$0")/.."
docker compose --profile e3 run --rm --no-deps transformar python -m semantico
