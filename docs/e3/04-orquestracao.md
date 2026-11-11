# Orquestração

O Dagster sobe no serviço `orquestrador` (porta 3000). O grafo da agenda diária, às 06:00 no horário de Brasília:

```text
lote_conferido → marts → publicar_consumo → freshness
```

`lote_conferido` só segue se `lote.internacao` tem snapshot. `marts` é o `dbt build`. `publicar_consumo` grava o schema `consumo` e tem retry: uma falha dispara uma segunda tentativa um segundo depois. `freshness` recusa a execução se a ocupação semanal estiver fora do SLA de 24 horas.

A opção nula desta parte é um cron com o SQL de `sql/e3/opcao_nula.sql`. Ela não tem grafo, não repete uma etapa que falhou e não preenche um ano sem apagar os outros. O [ADR 0003](../adr/0003-estrela-semanal-sobre-dbt.md) registra essa comparação.

## Retry

`publicar_consumo` falha de propósito se existir o arquivo `/app/var/falhar_publicacao`. A primeira tentativa apaga o arquivo e erra. A segunda não encontra o arquivo e publica.

```bash
scripts/demo_retry.sh
```

A saída fica em `medicoes/e3/retry_*.txt`. O perfil `e3` precisa estar no ar.

## Backfill

O asset `consumo_ano` é particionado de 2021 a 2026. Cada partição reconstrói os marts daquele ano e publica só essas linhas: apaga o ano no `consumo` e insere de novo, sem mexer nos outros anos.

```bash
scripts/demo_backfill.sh
```

O script primeiro publica só 2020, ano que esta carga não tem, e a ocupação fica vazia. Depois preenche cada ano que `int_semana` realmente tem. No fim recria os índices e atualiza os planos. A saída fica em `medicoes/e3/backfill_*.txt`.

Na amostra o mecanismo aparece sobre a competência versionada. A série de cinco anos aparece com `MODO=completo`.
