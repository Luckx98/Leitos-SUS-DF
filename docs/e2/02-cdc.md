# CDC

O caminho de CDC lê o WAL lógico do PostgreSQL e publica em `cdc.*`, com latência de segundos em vez do intervalo de agendamento do lote.

```text
PostgreSQL (wal_level=logical) → Debezium Server → Redpanda (API Kafka) → consumidor Python → cdc.* (Iceberg)
```

- **Debezium Server** (`infra/debezium/application.properties`) lê a publicação `leitos_cdc` (criada pela migração `0007`) via `pgoutput` e publica um tópico por tabela, em JSON comprimido com zstd por lote do produtor.
- **Redpanda** fala a API do Kafka num único nó — Kafka Connect + Kafka "completo" não cabem na máquina de referência.
- **O consumidor** (`lakehouse/cdc.py`) lê os tópicos, converte cada evento numa linha e grava no Iceberg.

## Por que o slot de replicação é do Debezium, não da migração

Um slot de replicação sem consumidor retém o WAL indefinidamente. Se a migração criasse o slot, qualquer ambiente que só usa a E1 (sem o perfil `e2`) acumularia WAL sem nunca ler. O slot só existe a partir da primeira vez que o Debezium sobe.

## Demonstração

```bash
docker compose --profile e2 up -d
scripts/demo_cdc.sh              # carrega DF 02/2025 e mede até cdc.internacao reconciliar
scripts/demo_cdc.sh GO 2025-03   # outra UF e competência
```

O script carrega uma competência nova (a origem só faz `INSERT`) e mede o tempo até `cdc.internacao` bater com a origem para aquela carga.

## Medido

| Cenário | Tempo | Pico de memória do consumidor |
| --- | ---: | ---: |
| Snapshot inicial (origem inteira, 3,67 milhões de internações) | ~15 min | perto do limite de memória configurado, nas três configurações testadas (ver limitação abaixo) |
| Competência nova (DF+GO), do fim da carga à reconciliação | 4 s | 553 MiB |

Reproduzir: `scripts/medir_ingestao.sh`, Fases 2 e 3. Resultado em `medicoes/e2/ingestao_2026-10-19.txt`.

## Limitação conhecida

O snapshot inicial — quando o CDC sobe contra uma origem já populada — faz o consumidor crescer até perto de qualquer limite de memória configurado (testado em 1.024 MiB e depois em 1.536 MiB; os dois ficaram a menos de 2 MiB do teto). Reduzir o tamanho do lote do consumidor e estreitar o filtro de deduplicação (de um intervalo de datas para um `In()` nas datas exatas) não resolveu. A causa mais provável é o acúmulo de metadado do Iceberg ao longo de várias dezenas de commits num único snapshot, mas isso não foi perfilado — ver o gatilho de revisão no [ADR 0002](../adr/0002-lote-incremental-e-cdc-sobre-iceberg.md#gatilho-de-revisao).

Trocar o modo de snapshot do Debezium para pular o histórico (`no_data`) foi considerado e descartado: o `cdc` não espera o `loader` terminar no Compose, então parte do que já está na origem ficaria fora de `cdc.*` para sempre, quebrando a reconciliação simples que `docker compose --profile e2 up` demonstra hoje.
