# Entrega 2 — Lakehouse alimentado por lote e CDC

A E2 constrói, a partir da origem OLTP da E1, um lakehouse em Iceberg para a camada analítica: um caminho em lote, incremental e barato, e um caminho de CDC, com latência de segundos. Os dois escrevem o mesmo esquema, em namespaces separados (`lote` e `cdc`), para poderem ser medidos e comparados.

## Onde está cada requisito

| Requisito da E2 | Onde está | Evidência no repositório |
| --- | --- | --- |
| Ingestão em lote idempotente e reexecutável | [Lote incremental](01-lote-incremental.md) | `lakehouse/lote.py`, `lakehouse/compactar.py` |
| Fluxo de mudanças a partir do OLTP (CDC) | [CDC](02-cdc.md) | `lakehouse/cdc.py`, `infra/debezium/` |
| Formato aberto, com particionamento e evolução de esquema | [Formato aberto](03-formato-aberto.md) | `lakehouse/esquemas.py`, `lakehouse/catalogo.py` |
| Semântica de entrega declarada e demonstrada | [Semântica de entrega](04-semantica-de-entrega.md) | `scripts/demo_semantica.sh` |
| Dado atrasado e reprocessamento de janela | [Dado atrasado](05-dado-atrasado.md) | `lakehouse/janela.py` |
| Serialização e compressão justificadas | [Serialização e compressão](06-serializacao-e-compressao.md) | `medicoes/e2/formatos_2026-10-19.txt` |
| ADR do mecanismo de ingestão, com opção nula | [ADR 0002](../adr/0002-lote-incremental-e-cdc-sobre-iceberg.md) | `scripts/medir_ingestao.sh`, `lakehouse/medir_iceberg_delta.py` |

## Resultado em números

| Medida | Valor |
| --- | ---: |
| Internações reconciliadas nos dois caminhos (carga completa) | 3.734.853 |
| Tempo do lote inicial (= custo da opção nula, recarga completa) | 103 s |
| Tempo do snapshot inicial do CDC (origem inteira) | 15 min (máquina de referência) |
| Latência do CDC numa competência nova, do fim da carga à reconciliação | 4 s |
| Tempo do lote incremental numa competência nova | 18 s |
| Formato de mensagem do CDC | JSON + zstd, 41 B/evento (1.004 B sem compressão) |
| Evolução de partição (mês → ano), Iceberg × Delta | 0,01 s (só metadado) × 0,42 s (reescreve a tabela) |

`docker compose --profile e2 up --build` sobe o perfil inteiro sobre a amostra da E1 em menos de um minuto, sem rede. A carga completa e as medições acima usam `MODO=completo`.
