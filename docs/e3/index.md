# Entrega 3 — camada analítica

A E3 responde à pergunta declarada na E1. O lakehouse da E2 guarda o dado; aqui ele vira um modelo dimensional, testado e reconstruído sozinho.

A fonte analítica é `lote.*`. O [ADR 0002](../adr/0002-lote-incremental-e-cdc-sobre-iceberg.md) deixou o lote como o caminho que reprocessa a janela de dado atrasado. O perfil `e3` não sobe Redpanda, Debezium nem o consumidor de CDC.

## Onde está cada requisito

| Requisito da E3 | Onde está | Evidência no repositório |
| --- | --- | --- |
| Fato, dimensão, granularidade e variação lenta | [Modelo dimensional](01-modelo-dimensional.md) | `transformacao/models/marts/` |
| Transformação declarativa em camadas | [Transformações](02-transformacoes.md) | `transformacao/` (dbt) |
| Testes de esquema, volume, unicidade, integridade e distribuição | [Testes](03-testes.md) | `transformacao/tests/`, `transformacao/models/marts/_marts.yml` |
| Orquestração com grafo, retry e backfill | [Orquestração](04-orquestracao.md) | `orquestracao/`, `scripts/demo_retry.sh`, `scripts/demo_backfill.sh` |
| Consulta otimizada com plano antes e depois | [Consulta otimizada](05-consulta-otimizada.md) | `sql/e3/indice.sql`, `medicoes/e3/explain_*.txt` |
| Freshness e SLA | [Freshness e SLA](06-freshness-e-sla.md) | `transformacao/models/marts/sla.sql`, `consumo.controle_freshness` |
| ADR de modelagem e ferramenta | [ADR 0003](../adr/0003-estrela-semanal-sobre-dbt.md) | `sql/e3/opcao_nula.sql` |
| Painel da pergunta da E1 | [Painel](07-painel.md) | `painel/app.py` |
| Experimento vetorial: cosseno não é o limiar | [Banco vetorial](08-banco-vetorial.md) | `semantico/`, `scripts/demo_vetor.sh` |

```bash
docker compose --profile e3 up --build
```

Sobe a origem, o lote, o `dbt build`, a publicação no schema `consumo`, o Dagster (porta 3000) e o painel (porta 8501). No modo `amostra` não precisa de rede. `MODO=completo` é o que produz a série de 2021 a 2025.
