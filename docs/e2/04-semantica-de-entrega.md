# Semântica de entrega

- **Lote:** exatamente uma vez. A marca d'água entra no mesmo commit dos dados; sem incremento, nada é gravado ([Lote incremental](01-lote-incremental.md)).
- **CDC:** o Debezium entrega **pelo menos uma vez** — depois de uma queda, pode reenviar eventos já publicados, com offsets novos no tópico. O consumidor (`lakehouse/cdc.py`) torna isso **efetivamente exatamente uma vez**:
    1. o offset de cada tópico é gravado como propriedade do snapshot do Iceberg, no mesmo commit dos dados; ao reiniciar, o consumidor retoma desse offset, não do confirmado no Redpanda;
    2. cada micro-lote é deduplicado pela chave de negócio da origem, dentro do lote e contra as linhas já gravadas na janela de datas que o lote toca.

## Demonstração

```bash
docker compose --profile e2 up -d
# espere cdc.* reconciliar com a origem, depois:
scripts/demo_semantica.sh
```

O script (`lakehouse/demo_semantica.py`) reexecuta o lote (nada é regravado), relê o CDC desde o offset 0 com deduplicação (nada é gravado), relê de novo sem deduplicação (tudo é gravado em duplicidade) e volta no tempo para o snapshot anterior.

## Medido (amostra, 20.995 internações)

| Passo | Eventos relidos | Gravadas | Duplicatas descartadas | Reconciliação |
| --- | ---: | ---: | ---: | --- |
| Releitura do offset 0, **com** deduplicação | 34.052 | 0 | 34.052 | `cdc.*` = origem, 0 duplicatas |
| A mesma releitura **sem** deduplicação | 34.052 | 34.052 | 0 | diverge: toda tabela com o dobro das linhas |
| Viagem no tempo ao snapshot anterior | — | — | — | `cdc.*` = origem de novo |

Resultado completo em `medicoes/e2/semantica_2026-10-19.txt`. A viagem no tempo usa `manage_snapshots().rollback_to_snapshot(...)` do Iceberg — o mesmo recurso que permitiria reconstruir o estado do lakehouse em qualquer ponto do passado, sem precisar de uma tabela de histórico separada.
