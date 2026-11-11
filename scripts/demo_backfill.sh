#!/bin/sh
# Esvazia o consumo e preenche, ano a ano, os anos que a carga tem. Exige o perfil e3 no ar.
set -eu
cd "$(dirname "$0")/.."
docker compose --profile e3 exec -T orquestrador python -m orquestracao.demo_backfill
