#!/bin/sh
# Primeira publicação falha de propósito; o retry conclui. Exige o perfil e3 no ar.
set -eu
cd "$(dirname "$0")/.."
docker compose --profile e3 exec -T orquestrador python -m orquestracao.demo_retry
