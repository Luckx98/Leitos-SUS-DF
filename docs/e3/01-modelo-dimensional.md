# Modelo dimensional

Estrela. Duas fontes já conciliadas na E1 (SIH e CNES), esquema estável desde a E2. A pergunta é agregação por semana e região. Data Vault acrescentaria hubs sem uma terceira fonte. Uma tabela única no grão paciente-dia mistura o leito, que não tem CID, com a internação.

A decisão e a medição dos dois grãos estão no [ADR 0003](../adr/0003-estrela-semanal-sobre-dbt.md).

## Granularidade

| Tabela | O que uma linha é |
| --- | --- |
| `dim_estabelecimento` | uma versão de cadastro de um estabelecimento, vigente de `valido_de` até a véspera da versão seguinte |
| `dim_semana` | uma semana ISO (a segunda-feira) em uma UF, com a marca de mês provisório daquela UF |
| `dim_regiao_saude` | uma região de saúde |
| `dim_cid` | um código CID-10, com o capítulo |
| `fato_internacao` | uma AIH paga na carga vigente, ligada à versão do estabelecimento vigente no mês da saída |
| `ocupacao_semana_regiao` | uma região de saúde em uma semana ISO: paciente-dia, leitos SUS, ocupação e o indicador acima de 85% |
| `causa_semana_regiao` | uma região, uma semana ISO e um capítulo da CID-10, com a parcela dos paciente-dias da semana |

O consumo fica no grão grosso. O paciente-dia existe como view (`intermediate.int_paciente_dia`) para construir os dois fatos e não é publicado: guardá-lo não muda a resposta e multiplica a linha pelo tempo de permanência.

A expansão do dia é a da L4: de `dt_saida - dias_permanencia` até a véspera da saída. Na longa permanência, `dt_internacao` é a data original, não o início do período cobrado.

## Variação lenta

`dim_estabelecimento` é tipo 2. A origem já grava uma linha nova quando gestão, natureza jurídica, mantenedora ou município mudam (`estabelecimento_versao`, competência a competência). A dimensão não sobrescreve: a vigência vai de `competencia_inicio` até a véspera da versão seguinte.

A internação junta a versão vigente no mês de `dt_saida`, não a versão de hoje. A L4 da E1 usa `DISTINCT ON (cnes) ... ORDER BY competencia_inicio DESC`, que reescreve o passado com o cadastro atual. Se a saída é anterior à primeira versão conhecida, entra a primeira versão e a coluna `cadastro_posterior` fica verdadeira.

A região do hospital do DF vem da tabela curada, porque o município no DATASUS é um só (530010). Em Goiás, a região vem do município. As duas entram na versão, então uma mudança de município muda a região a partir daquela competência.
