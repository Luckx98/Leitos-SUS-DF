# ADR 0003 — Estrela semanal, construída com dbt, publicada no Postgres

- **Status:** Aceito
- **Data:** 2026-11-04
- **Decisores:** Squad Grupo 01 (Leitos SUS-DF)

## Contexto

A pergunta da E1 pede as semanas de 2021–2025 em que a ocupação estimada (paciente-dia ÷ leitos SUS × 7) passou de 85% em cada região de saúde do DF, e os capítulos da CID nesse excesso. A L4 calcula isso na origem e leva **6,4 s para um único ano**, porque espalha cada internação em dias ([caracterização da carga](../e1/05-caracterizacao-da-carga.md)).

A E2 deixou o dado em `lote.*`, no caminho que reprocessa a janela de dado atrasado ([ADR 0002](0002-lote-incremental-e-cdc-sobre-iceberg.md)). A E3 materializa a conta a partir daí.

**Carga de trabalho:**

| Aspecto | Medida |
| --- | --- |
| Leitura que a pergunta repete | expansão de paciente-dia na origem: 6,4 s para 2024 |
| Grão da resposta | uma linha por região de saúde por semana ISO, mais uma linha por região, semana e capítulo da CID-10 |
| Latência tolerada | horas; a fonte do DATASUS é mensal |
| Máquina | 8 CPUs, cerca de 6 GB. O perfil `e3` não sobe o CDC junto com a transformação |

**Restrições:** software livre, SQL e Python, o mesmo DuckDB 1.5.6 da imagem, e a amostra (DF, 01/2025) tem de subir sem rede.

## Alternativas consideradas — modelo

| | Alternativa | Prós | Custos |
| --- | --- | --- | --- |
| 0 | **Tabela única no grão paciente-dia × CID.** Uma linha por dia de permanência e por causa | uma consulta só, sem junção | o leito não tem CID; misturar os dois estoura o volume e o grão da pergunta é a semana |
| 1 | **Data Vault.** Hubs de internação, leito e estabelecimento, com links e satélites | aguenta uma terceira fonte sem reescrever o fato | SIH e CNES já foram conciliados na E1; a pergunta é agregação, e o hub não responde semana e região |
| 2 | **Estrela no grão da semana.** Fato de ocupação e fato de causa, com a dimensão do estabelecimento em variação lenta | o painel lê a linha que a pergunta pede; a versão do cadastro não reescreve o passado | duas tabelas de fato; o paciente-dia continua existindo na transformação, só não é publicado |

## Alternativas consideradas — ferramenta

| | Alternativa | Prós | Custos |
| --- | --- | --- | --- |
| 0 | **Opção nula: um SQL no cron.** `sql/e3/opcao_nula.sql` é a L4 sem o filtro de 2024, na origem, com o cadastro mais recente | nenhum projeto a mais; a consulta já existe | sem camada, sem teste de distribuição, sem grafo, e o `DISTINCT ON (cnes) ... competencia_inicio DESC` reescreve a série com a gestão de hoje |
| 1 | **SQLMesh** | transformação declarativa, com plano e teste | a equipe não tem um projeto SQLMesh; o DuckDB da imagem já é o motor do dbt-duckdb |
| 2 | **dbt (dbt-duckdb)** | camadas, teste de esquema, unicidade, relacionamento e teste singular; o grafo é o do `dbt build` | mais um processo na máquina; o mart precisa ser copiado para o Postgres para o `EXPLAIN (ANALYZE, BUFFERS)` e para o painel |

O orquestrador segue a mesma conta. A opção nula é o cron com esse SQL. O Dagster acrescenta a agenda, o retry de uma etapa e o backfill de um ano sem apagar os outros.

## Medição

**1. Custo de recalcular na origem.** Já está no repositório: L4, ocupação semanal de 2024, **6,4 s** (`docs/e1/05-caracterizacao-da-carga.md`). Esse é o número que justifica materializar a semana uma vez.

**2. Os dois grãos, no recorte que valida o SQL.** 20 AIHs sintéticas, um estabelecimento, janeiro de 2025, DuckDB 1.5.6. Resultado em `medicoes/e3/granularidade_2026-11-04.txt`.

| Grão | Linhas | Leitura (mediana de 5) |
| --- | ---: | ---: |
| Fino: agregar `int_paciente_dia` na hora | 80 paciente-dias | 1,29 ms |
| Grosso: ler `ocupacao_semana_regiao` | 4 semanas | 0,14 ms |

O fino é mais barato de *não* guardar: a resposta não muda e a linha cresce com a permanência. No mesmo recorte o `dbt build` fechou com 77 passos sem erro. A semana de 2025-01-06 ficou com ocupação 1,1429 (80 paciente-dias, 10 leitos). As duas versões do cadastro permaneceram: gestão M até 2025-02-28 e gestão E a partir de 2025-03-01. A internação de janeiro usa M, não a versão de março.

Esse recorte não é a amostra nem a carga completa. `python -m transformacao`, no perfil `e3`, reescreve o arquivo com o tempo do lakehouse e o tempo da opção nula no Postgres. Nesta sessão o Docker não estava no ar (`~/.docker/run/docker.sock` ausente; o Desktop pede senha de administrador para o vmnetd), então o `EXPLAIN (ANALYZE, BUFFERS)` e o tempo do SQL nulo na origem não foram medidos. O SQL dos dois está no repositório (`sql/e3/opcao_nula.sql`, `sql/e3/indice.sql`) e `transformacao/explicar.py` grava os planos em `medicoes/e3/explain_*.txt`.

## Decisão

Estrela no grão da semana, construída com dbt em três camadas sobre `lote.*`, publicada no schema `consumo`. O paciente-dia fica como view. A dimensão do estabelecimento é variação lenta tipo 2, ligada pelo mês da saída. O Dagster agenda o grafo, repete a publicação que falha e preenche um ano por vez.

## Consequências

- A L4 deixa de ser a consulta do painel. Ela continua no repositório como o plano da origem, para comparar com o mart.
- Uma gestão que muda em março não altera a ocupação de janeiro. O teste `teste_scd_sem_sobreposicao` falha se duas vigências do mesmo CNES se cruzarem.
- O perfil `e3` compartilha SeaweedFS, catálogo e lote com o `e2`, e não sobe Redpanda, Debezium nem o consumidor de CDC.
- Na amostra o painel cobre a competência versionada e avisa que 2021–2025 exige `MODO=completo`. O teste de buraco olha os meses que existem; o de série completa só liga nesse modo.
- O SLA é de 24 horas entre o avanço do lote e `consumo.ocupacao_semana_regiao`. A agenda é diária, às 06:00.
