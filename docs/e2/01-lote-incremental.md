# Lote incremental

O caminho de lote (`lakehouse/lote.py`) exporta a origem para `lote.*` (`carga`, `estabelecimento`, `estabelecimento_versao`, `leito`, `internacao`) sem depender de um sinal externo de mudança: como a origem é insert-only e toda linha aponta para a carga que a trouxe (E1), o incremento é só "tudo com `id_carga` maior que o último exportado".

```bash
docker compose run --rm --no-deps lote    # roda uma vez; o serviço já roda depois da carga
```

## Idempotência

A marca d'água (`lote.id_carga_max`) é gravada como **propriedade do snapshot do Iceberg, no mesmo commit dos dados**: ou os dois entram juntos, ou nenhum entra. Não há uma tabela de controle separada para sincronizar.

- **Reexecutar sem incremento não grava nada.** Medido: a segunda chamada sobre a mesma carga completa não cria snapshot em nenhuma tabela.
- **Falha no meio não deixa estado parcial.** A exportação de uma tabela é uma única transação do Iceberg (`lakehouse/lote.py:98`); se cair antes do commit, a tabela fica exatamente como estava.
- **Pressuposto declarado:** as cargas se confirmam na ordem do `id_carga`. Dois loaders em paralelo poderiam confirmar o 11 antes do 10, e o 10 ficaria para trás da marca — por isso o `docker-compose.yml` roda um loader por vez.

## O que acontece numa execução

1. Lê a origem em `REPEATABLE READ`, para a marca superior (`max(id_carga)`) e as linhas lidas vierem do mesmo instante.
2. Exporta cada tabela em blocos de 250 mil linhas (cursor nomeado, sem carregar tudo em memória).
3. Se alguma internação nova chegou, reprocessa a janela de dado atrasado ([Dado atrasado](05-dado-atrasado.md)).
4. Compacta os arquivos pequenos que o incremento e a janela deixaram.

## Medido (carga completa, DF+GO)

| Execução | Tempo | Pico de memória |
| --- | ---: | ---: |
| Lote inicial (= custo da opção nula, recarga completa) | 103 s | 1.501 MiB |
| Lote incremental, uma competência nova (DF+GO) | 18 s | 664 MiB |
| Reexecução sem incremento | < 1 s | — |

Reproduzir: `scripts/medir_ingestao.sh`, Fases 1 e 3. Resultado em `medicoes/e2/ingestao_2026-10-19.txt`. Mais sobre a escolha deste mecanismo frente à opção nula e ao CDC: [ADR 0002](../adr/0002-lote-incremental-e-cdc-sobre-iceberg.md).
