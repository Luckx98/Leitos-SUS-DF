#!/bin/sh
# Opção nula da E3: a pergunta calculada direto na origem, sem dbt e sem grafo.
set -eu
cd "$(dirname "$0")/.."
docker compose exec -T postgres psql -U "${POSTGRES_USER:-leitos}" -d "${POSTGRES_DB:-leitos}" -f - < sql/e3/opcao_nula.sql
