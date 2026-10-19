# ADR 0002 — O lakehouse ingere por lote incremental e por CDC, sobre Iceberg

- **Status:** Aceito
- **Data:** 2026-10-19
- **Decisores:** Squad Grupo 01 (Leitos SUS-DF)

## Contexto

A E2 exige um lakehouse alimentado a partir da origem OLTP da E1 (insert-only, `wal_level=logical`; ver [ADR 0001](0001-origem-insert-only-versionada-por-competencia.md)), com formato aberto, um fluxo de mudanças a partir do OLTP, semântica de entrega declarada e demonstrada, e reprocessamento do dado atrasado.

**Carga de trabalho** (medida na carga completa, DF e GO, 01/2021 a 08/2026; `medicoes/e2/ingestao_2026-10-19.txt` e `medicoes/e2/iceberg_delta_2026-10-19.txt`):

| Aspecto | Medida |
| --- | --- |
| Volume na origem | 3,73 milhões de internações, 243 mil linhas de leito, 26 mil estabelecimentos |
| Crescimento | cerca de 200 MB/ano na origem ([ADR 0001](0001-origem-insert-only-versionada-por-competencia.md)) |
| Escrita (incremento mensal) | uma competência nova (08/2026, DF+GO): 60.723 internações em 34 s de carga |
| Leitura | analítica: agregações por ano/região/CID sobre o lakehouse (DuckDB); a pergunta de gestão já mostrou, na E1, que a origem OLTP não escala para isso (7,5 s para um ano) |
| Latência tolerada | horas, a partir do instante em que o dado entra na origem (não da competência do DATASUS, já coberta pela janela de maturidade da E1) |

**Restrições não funcionais:**

- Tudo sobe com `docker compose --profile e2 up`, na mesma máquina de estudante da E1 (8 CPUs, 5,7 a 7,3 GB de RAM observados em duas máquinas diferentes).
- Somente software livre; sem depender de um cluster Java/Scala (Spark, Kafka Connect completo) que não cabe nessa máquina.
- A equipe domina SQL e Python.
- O formato de tabela precisa ser lido pelo DuckDB sem reimplementar o motor de consulta.
- O PostgreSQL já está pronto para CDC lógico desde a E1.

## Alternativas consideradas — mecanismo de ingestão

| | Alternativa | Prós | Custos |
| --- | --- | --- | --- |
| 0 | **Opção nula: recarga completa agendada.** Um `INSERT ... SELECT` (ou reexportação completa) roda periodicamente, sem marca d'água, reconstruindo o lakehouse do zero | mais simples de implementar; sem estado para corromper | custo de cada execução cresce com o volume total, não com o incremento (medido: 103 s e 1,5 GiB de pico para reescrever tudo); latência = intervalo do agendamento |
| 1 | **Lote incremental agendado.** Exporta por marca d'água de `id_carga`, grava no mesmo commit do snapshot do Iceberg, reprocessa a janela dos últimos 3 meses para o dado atrasado | custo proporcional só ao incremento (medido: 18 s para uma competência nova); idempotente; falha no meio não grava nada | latência = intervalo do agendamento, não da escrita na origem |
| 2 | **CDC (Debezium → Redpanda → consumidor Python).** Lê o WAL lógico e publica em tópicos; o consumidor grava no Iceberg com offset no snapshot | latência de segundos (medido: 1,8 a 25,6 s de latência média por tabela); sem agendamento | três serviços extras (SeaweedFS, Redpanda, Debezium); snapshot inicial caro e disputando memória com os outros serviços (ver Medição); frágil sob pressão de memória |

Kafka Connect + Kafka "completo" (sem o Redpanda) foi descartado antes de medir: a soma de memória dos dois já não cabe na máquina de referência, e o Debezium Server fala a mesma API Kafka do Redpanda sem precisar do Connect.

## Alternativas consideradas — formato de tabela

| | Alternativa | Prós | Custos |
| --- | --- | --- | --- |
| 0 | **Opção nula: Parquet solto**, sem camada de tabela | mais simples; menos dependências | sem transação entre arquivos, sem *time travel*, sem evolução de esquema ou de partição; o consumidor do lote/CDC teria que inventar sua própria marca d'água fora do armazenamento |
| 1 | **Delta Lake** | formato colunar aberto; biblioteca Python sem JVM (`deltalake`/`delta-rs`) | particionamento é físico (pasta por valor); mudar a coluna de partição exige reescrever a tabela inteira |
| 2 | **Iceberg** (`pyiceberg`) | particionamento oculto (mudar a partição é só metadado); catálogo SQL cabe no mesmo Postgres da origem; escrita sem JVM | ecossistema Python mais novo que o do Delta; `pyiceberg` 0.12 não escreve em fluxo numa tabela particionada (contornado com `delete`+`append` em bloco, ver `lakehouse/janela.py`) |

## Medição

**1. Custo dos três mecanismos de ingestão.** Reproduzir: `scripts/medir_ingestao.sh` sobre a carga completa. Resultado em `medicoes/e2/ingestao_2026-10-19.txt` (máquina: 8 CPUs, 5,7 GiB de RAM).

| Fase | Tempo | Pico de memória |
| --- | ---: | ---: |
| Lote inicial = custo da opção nula | 103 s | 1.501 MiB (container do lote) |
| Snapshot do CDC (origem inteira) | 919 s (~15 min) | 1.024 MiB (container do cdc, no limite) |
| Competência nova — carga | 34 s | — |
| Competência nova — CDC alcança a origem | 4 s depois da carga | 553 MiB |
| Competência nova — lote incremental | 18 s | 664 MiB |

O snapshot do CDC ficou parado em 3.638.949 de 3.669.874 internações entre 685 s e 886 s — o consumidor bate no limite de memória exatamente no fim do snapshot, quando o Iceberg já acumulou dezenas de commits pequenos. Em 19/10/2026, numa segunda máquina (7,3 GiB), o mesmo snapshot (3,73 milhões de internações) chegou a 1.022–1.024 MiB mesmo depois de reduzir o lote do consumidor (50.000 → 20.000 linhas) e trocar o filtro de deduplicação por um `In()` nas datas exatas em vez de um intervalo min-máx (`lakehouse/cdc.py`, commit `96073e7` para a correção equivalente em `reconciliar.py`) — as duas mudanças não resolveram o limite, então o `mem_limit` do serviço `cdc` subiu de `1g` para `1536m` como ajuste pragmático (ver Consequências).

**2. Iceberg × Delta**, mesmos dados (internações com saída em 2024, 696.700 linhas), Parquet zstd em disco local para isolar o formato do armazenamento. Reproduzir: `docker compose run --rm --no-deps loader python -m lakehouse.medir_iceberg_delta`. Resultado em `medicoes/e2/iceberg_delta_2026-10-19.txt`.

| | escrita | tamanho | leitura (DuckDB) | evolução de esquema | evolução de partição (mês→ano) |
| --- | ---: | ---: | ---: | --- | --- |
| Iceberg | 0,5 s | 13,1 MB | 7,8 ms | 0,04 s, 0 arquivos reescritos | **0,01 s, só metadado** |
| Delta | 0,7 s | 16,6 MB | 11,6 ms | 0,01 s, 0 arquivos reescritos | **0,42 s, reescreve a tabela inteira** e muda a coluna física — quem filtrava por `dt_saida_mes` precisa mudar a consulta |

A evolução de partição é o critério decisivo: esta própria entrega precisou mudar a partição de mês para ano (`medicoes/e2/formatos_2026-10-19.txt`), e com Iceberg isso custou metadado; com Delta custaria reescrever a tabela inteira a cada mudança — e a reescrita cresce com o tamanho da tabela, não com o que mudou.

**3. Semântica de entrega**, demonstrada sobre a amostra (20.995 internações). Reproduzir: `scripts/demo_semantica.sh` com o perfil `e2` no ar. Resultado em `medicoes/e2/semantica_2026-10-19.txt`.

| Passo | Eventos relidos | Gravadas | Duplicatas descartadas | Reconciliação |
| --- | ---: | ---: | ---: | --- |
| Releitura do offset 0, com deduplicação | 34.052 | 0 | 34.052 | `cdc.*` = origem, 0 duplicatas |
| A mesma releitura sem deduplicação | 34.052 | 34.052 | 0 | `cdc.*` diverge: toda tabela com o dobro das linhas |
| Viagem no tempo ao snapshot anterior | — | — | — | `cdc.*` = origem de novo |

O Debezium entrega pelo menos uma vez (pode reenviar o que já publicou); o offset de cada tópico é gravado como propriedade do snapshot do Iceberg, no mesmo commit dos dados, e cada lote é deduplicado pela chave de negócio contra o que já está gravado. O resultado é **efetivamente exatamente uma vez** no Iceberg — demonstrado acima pela releitura completa sem gerar nenhuma linha nova, e pelo *rollback* que restaura o estado exato de antes de uma reexecução sem deduplicação.

## Decisão

O lakehouse mantém **os dois caminhos de ingestão, com papéis distintos**, escrevendo no formato **Iceberg**:

- o **lote** incremental é o caminho principal: mais barato, idempotente, e o único que reprocessa a janela de dado atrasado (`lakehouse/janela.py`) e compacta arquivos pequenos;
- o **CDC** cobre o que o lote não cobre — latência de segundos — e não substitui o lote: o snapshot inicial dele é caro e disputa memória com os outros serviços, então ele não é o caminho usado para a carga inicial ou para reprocessamento em massa;
- o namespace `cdc.*` existe em paralelo ao `lote.*` com o mesmo esquema de propósito: permitir medir e comparar os dois caminhos (esta medição), não como redundância de produção;
- o `mem_limit` do serviço `cdc` sobe de `1g` para `1536m`: as duas tentativas de reduzir o uso de memória (lote menor, filtro mais estreito) não resolveram o limite, e o diagnóstico (acúmulo de commits pequenos no Iceberg ao longo do snapshot) é um problema de manutenção do catálogo, não de como o consumidor lê cada lote — ver Gatilho de revisão.

## Consequências

**Ganhos**

- O lote sozinho já atende a latência tolerada (horas); o CDC é o que permite declarar e demonstrar uma semântica de entrega de segundos, item explícito do checklist da E2.
- A evolução de partição de mês para ano, que esta entrega precisou fazer, custou metadado (0,01 s) por ser Iceberg; em Delta teria custado reescrever a tabela inteira.
- Os dois caminhos gravando o mesmo esquema permitem reconciliar origem × lote × CDC por carga (`lakehouse/reconciliar.py`), uma evidência que um caminho só não daria.

**Perdas**

- Manter o CDC custa três serviços extras (SeaweedFS, Redpanda, Debezium) somando ao menos 1,9 GiB de memória reservada (384 + 768 + 768 MiB), mais o consumidor (agora até 1.536 MiB) — bem mais do que o lote sozinho.
- O SeaweedFS reiniciou sozinho, sob pressão de memória, duas vezes durante os testes de carga completa desta sessão (19/10/2026), interrompendo a exportação do lote no meio (recuperado ao reexecutar — a carga é idempotente, mas é uma fragilidade operacional real).
- `pyiceberg` 0.12 não escreve em fluxo numa tabela particionada: o reprocessamento da janela precisa de `delete` seguido de `append` em bloco, em vez de uma única operação.
- Arquivos antigos de partições reescritas pela janela ficam no S3 até os snapshots antigos do Iceberg expirarem — não há expiração automática configurada ainda.

**Irreversibilidade**

Desistir do CDC e manter só o lote é reversível e barato: basta parar o serviço `cdc` e remover o namespace `cdc.*` (usado só para comparação, não é referenciado por nenhuma consulta de produção). Desistir do lote não é: só ele reprocessa a janela de dado atrasado e só ele compacta os arquivos pequenos do CDC; sem o lote, a mesma lógica teria que ser reescrita dentro do consumidor de CDC.

## Gatilho de revisão

Revisar se ocorrer qualquer uma destas condições:

- o pico de memória do `cdc` passar de **1.536 MiB** mesmo depois do ajuste desta ADR — sinal de que o problema é o acúmulo de metadado do Iceberg ao longo do snapshot (não a folga de memória), e a correção passa a ser compactar manifests durante o próprio snapshot, não aumentar o limite de novo;
- o SeaweedFS voltar a reiniciar sob carga depois do ajuste de memória — trocar o armazenamento de objetos;
- alguma pergunta da plataforma passar a exigir, de forma sistemática, latência de segundos (hoje tolerada em horas) — o papel do lote como caminho principal deixa de se sustentar, e caberia reavaliar se o CDC vira o caminho único;
- `pyiceberg` liberar escrita em fluxo numa tabela particionada — simplificar `lakehouse/janela.py`, removendo o `delete`+`append` em bloco.
