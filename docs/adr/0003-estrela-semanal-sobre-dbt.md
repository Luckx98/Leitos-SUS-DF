# ADR 0003 — Estrela semanal, construída com dbt, publicada no Postgres

- **Status:** Aceito
- **Data:** 2026-11-04
- **Decisores:** Squad Grupo 01 (Leitos SUS-DF)

## Contexto

A pergunta da E1 pede as semanas de 2021–2025 em que a ocupação estimada (paciente-dia ÷ leitos SUS × 7) passou de 85% em cada região de saúde do DF, e os capítulos da CID nesse excesso. A L4 calcula isso na origem e leva **6,4 s para um único ano**, porque espalha cada internação em dias ([caracterização da carga](../e1/05-caracterizacao-da-carga.md)).

A E2 deixou o dado em `lote.*`, no caminho que reprocessa a janela de dado atrasado ([ADR 0002](0002-lote-incremental-e-cdc-sobre-iceberg.md)). A E3 materializa a conta a partir daí.

**Carga de trabalho:**

| Aspecto                       | Medida                                                                                               |
| ----------------------------- | ---------------------------------------------------------------------------------------------------- |
| Leitura que a pergunta repete | expansão de paciente-dia na origem: 6,4 s para 2024                                                  |
| Grão da resposta              | uma linha por região de saúde por semana ISO, mais uma linha por região, semana e capítulo da CID-10 |
| Latência tolerada             | horas; a fonte do DATASUS é mensal                                                                   |
| Máquina                       | 8 CPUs, cerca de 6 GB. O perfil `e3` não sobe o CDC junto com a transformação                        |

**Restrições:** software livre, SQL e Python, o mesmo DuckDB 1.5.6 da imagem, e a amostra (DF, 01/2025) tem de subir sem rede.

## Alternativas consideradas — modelo

|     | Alternativa                                                                                                          | Prós                                                                                  | Custos                                                                                              |
| --- | -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| 0   | **Tabela única no grão paciente-dia × CID.** Uma linha por dia de permanência e por causa                            | uma consulta só, sem junção                                                           | o leito não tem CID; misturar os dois estoura o volume e o grão da pergunta é a semana              |
| 1   | **Data Vault.** Hubs de internação, leito e estabelecimento, com links e satélites                                   | aguenta uma terceira fonte sem reescrever o fato                                      | SIH e CNES já foram conciliados na E1; a pergunta é agregação, e o hub não responde semana e região |
| 2   | **Estrela no grão da semana.** Fato de ocupação e fato de causa, com a dimensão do estabelecimento em variação lenta | o painel lê a linha que a pergunta pede; a versão do cadastro não reescreve o passado | duas tabelas de fato; o paciente-dia continua existindo na transformação, só não é publicado        |

## Alternativas consideradas — ferramenta

|     | Alternativa                                                                                                                 | Prós                                                                                              | Custos                                                                                                                                        |
| --- | --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| 0   | **Opção nula: um SQL no cron.** `sql/e3/opcao_nula.sql` é a L4 sem o filtro de 2024, na origem, com o cadastro mais recente | nenhum projeto a mais; a consulta já existe                                                       | sem camada, sem teste de distribuição, sem grafo, e o `DISTINCT ON (cnes) ... competencia_inicio DESC` reescreve a série com a gestão de hoje |
| 1   | **SQLMesh**                                                                                                                 | transformação declarativa, com plano e teste                                                      | a equipe não tem um projeto SQLMesh; o DuckDB da imagem já é o motor do dbt-duckdb                                                            |
| 2   | **dbt (dbt-duckdb)**                                                                                                        | camadas, teste de esquema, unicidade, relacionamento e teste singular; o grafo é o do `dbt build` | mais um processo na máquina; o mart precisa ser copiado para o Postgres para o `EXPLAIN (ANALYZE, BUFFERS)` e para o painel                   |

O orquestrador segue a mesma conta. A opção nula é o cron com esse SQL. O Dagster acrescenta a agenda, o retry de uma etapa e o backfill de um ano sem apagar os outros.

## Medição

**1. Custo de recalcular na origem.** Já está no repositório: L4, ocupação semanal de 2024, **6,4 s** (`docs/e1/05-caracterizacao-da-carga.md`). Esse é o número que justifica materializar a semana uma vez.

**2. Os dois grãos, no recorte que valida o SQL.** 20 AIHs sintéticas, um estabelecimento, janeiro de 2025, DuckDB 1.5.6. Resultado em `medicoes/e3/granularidade_2026-11-04.txt`.

| Grão                                     |           Linhas | Leitura (mediana de 5) |
| ---------------------------------------- | ---------------: | ---------------------: |
| Fino: agregar `int_paciente_dia` na hora | 80 paciente-dias |                1,29 ms |
| Grosso: ler `ocupacao_semana_regiao`     |        4 semanas |                0,14 ms |

O fino é mais barato de _não_ guardar: a resposta não muda e a linha cresce com a permanência. No mesmo recorte o `dbt build` fechou com 77 passos sem erro. A semana de 2025-01-06 ficou com ocupação 1,1429 (80 paciente-dias, 10 leitos). As duas versões do cadastro permaneceram: gestão M até 2025-02-28 e gestão E a partir de 2025-03-01. A internação de janeiro usa M, não a versão de março.

Esse recorte não é a amostra nem a carga completa.

**3. Amostra no perfil `e3`, em 2026-11-11.** DF, competência 01/2025: 20.995 internações, 122.450 paciente-dias, 28 semanas e 1.875 linhas de causa. `dbt build` com 77 passos sem erro, em 6,5 s. A opção nula na origem levou 1,0 s (28 linhas; nenhuma semana acima de 85% nesse mês). Ler o mart no Postgres levou 11,8 ms. Agregar o paciente-dia já materializado levou 4,0 ms; ler a semana levou 0,5 ms. Arquivo: `medicoes/e3/amostra/granularidade_2026-11-11.txt`. O `EXPLAIN` da L4 nessa origem levou 774 ms (`medicoes/e3/amostra/explain_l4_origem.txt`). O de um ano na carga da E1 continua sendo os 6,4 s.

**4. O índice, na mesma amostra.** `fato_internacao` filtrado por CNES e data de saída saiu de varredura sequencial (2,51 ms, 392 páginas) para `Bitmap Index Scan` em `idx_fato_internacao_cnes_saida` (1,16 ms). A ocupação semanal tem 28 linhas: o planejador ficou na varredura antes e depois do índice, como previsto. Os planos estão em `medicoes/e3/amostra/explain_*.txt`.

O retry da publicação pediu a segunda tentativa e concluiu (`medicoes/e3/retry_2026-11-11.txt`). O backfill de 2020 esvaziou o consumo; o de 2025 devolveu as 28 linhas (`medicoes/e3/backfill_2026-11-11.txt`).

**5. Série 2021–2026, `MODO=completo`, na mesma data.** DF e GO. A amostra de 01/2025 tinha entrado antes do histórico, e o loader descartava uma versão de cadastro quando já existia uma posterior. O leito de 2023 e 2024 do DF ficava sem estabelecimento, a ocupação passava de 500% em 122 semanas e `teste_serie_completa` falhava. `python -m loader.repor_versoes` releu os ST já baixados e inseriu 7.623 versões anteriores, numa carga nova, para o lote exportar. Depois disso o `dbt build` fechou com 77 passos em 21,4 s.

| Medida                                                        |      Valor |
| ------------------------------------------------------------- | ---------: |
| Internações em `fato_internacao`                              |  3.796.467 |
| Paciente-dias (não publicados)                                | 19.091.193 |
| Semanas × região                                              |      7.500 |
| Causa × semana × capítulo                                     |    128.515 |
| Semanas acima de 85% no mart                                  |        207 |
| Ler essas semanas no Postgres                                 |    41,8 ms |
| Agregar o paciente-dia já materializado                       |     177 ms |
| Opção nula na origem (7.500 linhas, 206 semanas acima de 85%) |     55,5 s |
| `EXPLAIN (ANALYZE, BUFFERS)` da mesma SQL                     |    165,9 s |

A opção nula usa o cadastro de hoje e conta uma semana a menos acima de 85%. O arquivo é `medicoes/e3/granularidade_2026-11-11.txt`. A amostra continua em `medicoes/e3/amostra/`.

No fato, o estabelecimento com mais AIHs (CNES 0010456, saídas de 2021 a 2025) foi mais rápido na varredura paralela (204,5 ms) do que no `Bitmap Index Scan` de `(cnes, dt_saida)` (376,0 ms): o predicado devolve cerca de 132 mil linhas. Na amostra, com 2.285 linhas, a varredura levava 2,51 ms e o índice 1,16 ms. A ocupação da região 52011 em 2026, filtrada em `ocupacao >= 0,85`, não tem linha; a varredura levou 0,64 ms e o índice 0,17 ms. Os planos da série estão em `medicoes/e3/explain_*.txt`.

## Decisão

Estrela no grão da semana, construída com dbt em três camadas sobre `lote.*`, publicada no schema `consumo`. O paciente-dia fica como view. A dimensão do estabelecimento é variação lenta tipo 2, ligada pelo mês da saída. O Dagster agenda o grafo, repete a publicação que falha e preenche um ano por vez.

## Consequências

- A L4 deixa de ser a consulta do painel. Ela continua no repositório como o plano da origem, para comparar com o mart.
- Uma gestão que muda em março não altera a ocupação de janeiro. O teste `teste_scd_sem_sobreposicao` falha se duas vigências do mesmo CNES se cruzarem.
- O perfil `e3` compartilha SeaweedFS, catálogo e lote com o `e2`, e não sobe Redpanda, Debezium nem o consumidor de CDC.
- Na amostra o painel cobre a competência versionada. `MODO=completo` publica a série, e `teste_serie_completa` exige 2021–2025 no DF. O teste de buraco olha os meses que a carga tem.
- Uma versão posterior do CNES não cobre os meses anteriores. O loader grava a primeira competência conhecida mesmo quando uma versão futura tem os mesmos atributos. Sem isso, a amostra de 01/2025 apaga o cadastro de 2021–2024.
- O SLA é de 24 horas entre o avanço do lote e `consumo.ocupacao_semana_regiao`. A agenda é diária, às 06:00.
