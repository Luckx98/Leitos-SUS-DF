# Transformações

O projeto dbt está em `transformacao/`. O motor é o DuckDB, que já lê Iceberg na imagem.

## Medalhões

| Medalhão | Onde fica | O que é uma linha daqui |
| --- | --- | --- |
| Bronze | Iceberg `lote.*` | o dado como chegou do lote, com todas as cargas, não só a vigente |
| Bronze paralelo | Iceberg `cdc.*` | o mesmo esquema, pelo CDC, só para comparar com a origem |
| Prata | DuckDB `staging` e `intermediate` | carga vigente, variação lenta, paciente-dia e a semana; não é publicado |
| Ouro | DuckDB `marts`, copiado para o Postgres `consumo` | a estrela da pergunta; é o que o painel e o `EXPLAIN` leem |

`cdc.*` não alimenta a prata. A ponte de leitura do snapshot atual chama-se `espelho` no DuckDB (`transformacao/fontes.py`): views `iceberg_scan` de `lote.*` e a cópia das referências que ficaram no Postgres. Não é um medalhão.

Três camadas do dbt:

- **staging** — o snapshot atual de `lote.carga`, `lote.internacao`, `lote.leito`, `lote.estabelecimento_versao` e `lote.maturidade`, mais a cópia das referências que ficaram no Postgres (CID, município, região de saúde e a tabela curada do DF). A vigência da E1 entra aqui: por fonte, UF e competência, só a carga de maior `id_carga`.
- **intermediate** — a dimensão de variação lenta, a internação com a versão do mês da saída, o paciente-dia (view), o leito somado por região e mês, e a semana com a ocupação.
- **marts** — as tabelas de consumo. Um `dbt build` com `anos` preenchido restringe só os marts; as dimensões continuam inteiras.

`transformacao/fontes.py` resolve o `metadata_location` do catálogo SQL do Iceberg e cria as views `espelho.*` com `iceberg_scan`. Sem esse passo o dbt não enxerga o lakehouse.

Depois do build, `transformacao/publicar.py` copia os marts para o schema Postgres `consumo`. A publicação completa substitui as tabelas. A publicação de um ano apaga só as linhas daquele ano e insere de novo: é o que o backfill usa.

```bash
docker compose --profile e3 run --rm --no-deps transformar
```

A opção nula — o SQL da L4 direto na origem, sem camada e sem teste — está em `sql/e3/opcao_nula.sql`. Ela usa a versão mais recente do cadastro. A comparação com o dbt está no [ADR 0003](../adr/0003-estrela-semanal-sobre-dbt.md).
