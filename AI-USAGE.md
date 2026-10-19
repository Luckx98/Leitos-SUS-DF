# AI-USAGE.md — Squad Grupo 01 (Leitos SUS-DF)

Registro de uso de assistentes e agentes de IA no Projeto Integrado.

Este arquivo cumpre a [Política de Uso de IA](https://unb-bd2.github.io/Disciplina/uso-de-ia/)
da disciplina. Ele não é confissão nem formalidade: é o mesmo tipo de registro
que um ADR faz para decisões de arquitetura.

**Duas regras de forma.** Escreva **no momento do uso**, não na véspera da
Entrega — registro reconstruído de memória sai impreciso, e imprecisão aqui é o
que a política pune. E versione junto com o código: uma entrada por commit
relevante é melhor que um resumo mensal.

**Não precisa registrar** autocompletar de editor, correção ortográfica ou
tradução. Registre o que produziu artefato ou mudou uma decisão.

---

## Entradas

### 2026-10-07 — Remoção do código do tema anterior (GuiaOrientador/CAPES)

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5), extensão do VS Code.
- **Onde:** `src/` (API FastAPI, modelos ORM, pipeline CAPES e embeddings),
  `frontend/`, `scripts/`, `tests/test_capes.py`, `db/init/`, migração
  `20260930_0001`, ADR 0001 da CAPES; ajustes em `docker-compose.yml`,
  `Dockerfile`, `requirements.txt`, `.env.example`, `alembic/env.py` e `mkdocs.yml`.
- **O que foi pedido:** levantar o que do repositório servia ao novo tema e,
  depois, remover o que não servia mais.
- **O que foi aproveitado:** a remoção inteira e o diagnóstico. Ficaram o Alembic
  (que resolveu a pendência da ferramenta de migração), a ordem
  postgres → migrate → loader do Compose, o MkDocs e o workflow do Pages.
  Redis, SeaweedFS, API e dependências de IA (OpenAI, LangChain, pgvector) saíram.
  Os textos de documentação do tema antigo foram mantidos de propósito: estão
  com outra pessoa da Squad.
- **Como foi verificado:** busca por referências aos módulos apagados (nenhum
  import quebrado) e `docker compose config` sem erro. O commit da limpeza foi
  revisado e feito à mão (`ab25d3f`).
- **Quem revisou:** Cairo Florenço.

### 2026-10-07 — Região de saúde dos hospitais do DF (`estabelecimento_regiao_saude_df.csv`)

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5), extensão do VS Code.
- **Onde:** `dados/referencia/estabelecimento_regiao_saude_df.csv` e tabela
  `estabelecimento_regiao_df` (migração `0002`).
- **O que foi pedido:** medir os arquivos reais antes de modelar. A medição
  mostrou que no DF todo hospital e todo paciente têm o mesmo município (530010)
  e que o campo `REGSAUDE` do CNES é texto livre e quase sempre vazio, então não
  há como derivar a região de saúde das fontes. Das alternativas levantadas
  (tabela curada, CEP, mudar a pergunta), a Squad escolheu a tabela curada.
- **O que foi aproveitado:** a tabela com 56 estabelecimentos. Nome e bairro
  vêm da API pública do CNES (`apidadosabertos.saude.gov.br`). A região
  administrativa foi atribuída pelo assistente a partir do bairro e do endereço,
  e a região de saúde segue a composição da SES-DF, com os códigos do DATASUS
  (`df_regsaud.cnv`, 53002–53008). Dois casos ficaram marcados como incertos na
  coluna `observacao` (Setor Policial Sul e Núcleo Rural Alexandre Gusmão).
  Três hospitais de campanha da COVID-19 (Gama, Autódromo e Ceilândia) só
  apareceram na carga completa e foram acrescentados depois.
- **Como foi verificado:** a quantidade de regiões administrativas por região
  bateu com a quantidade de códigos de cada região no `df_regsaud.cnv`. Na carga
  completa, o loader avisa os CNES do DF sem região; depois do acréscimo dos três
  hospitais de campanha, o aviso deixou de aparecer.
  **Pendente:** conferir a atribuição contra a lista oficial da SES-DF.
  Hospitais de referência distrital (HBDF, HMIB, HCB, HUB, ICTDF) estão
  classificados só pela localização, o que infla a Região Central; isso será
  tratado na análise.
- **Quem revisou:** Cairo Florenço.

### 2026-10-07 — Banco de origem, migrações e loader

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5), extensão do VS Code.
- **Onde:** `docker-compose.yml`, `Dockerfile`, `alembic/versions/0001`–`0006`,
  `loader/`, `dados/amostra/`, `requirements.txt`.
- **O que foi pedido:** implementar o banco insert-only versionado por
  competência e a carga reprodutível de SIH/SUS (RD) e CNES (ST, LT) para DF e
  GO, conforme o plano da E1.
- **O que foi aproveitado:** tudo, com estas mudanças em relação ao plano,
  todas motivadas por medição dos arquivos reais:
  - a chave `(n_aih, competencia)` do plano não é única. AIHs de longa
    permanência (`IDENT=5`) aparecem mais de uma vez por competência; a chave
    passou a incluir `dt_saida`. Nesses registros `DT_INTER` é a data da
    internação original (há casos de 2008);
  - a chave de leito usa `CODLEITO`, não `TP_LEITO`;
  - campos identificadores (NASC, CEP, CPF_AUT, GESTOR_CPF) não são gravados;
  - CIDs ausentes do `cid10.dbf` do DATASUS (N18.2–N18.5 e U04/U09/U10) ficam
    rejeitados e contados em `carga_rejeicao`, por decisão da Squad.
  O assistente errou o parser dos arquivos `.cnv` na primeira versão (nenhuma
  região era reconhecida); o erro apareceu na primeira execução e foi corrigido.
- **Como foi verificado:** `docker compose up --build` numa cópia limpa do
  repositório, sem `.env`: as 6 migrações rodaram em ordem e a amostra carregou.
  `UPDATE` e `DELETE` foram recusados pelo trigger. Uma segunda execução ignorou
  todos os arquivos (idempotência por sha256). A carga completa (DF+GO,
  01/2021–07/2026, 406 arquivos) terminou sem falhas em 14 min 20 s, com
  3.669.874 internações, 240.132 linhas de leito, 30.919 versões de
  estabelecimento e 145 rejeições (0,004%).
- **Quem revisou:** Cairo Florenço.

### 2026-10-07 — Testes automatizados do loader

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5), extensão do VS Code.
- **Onde:** `tests/test_dbf.py`, `tests/test_referencias.py`,
  `tests/test_sih.py`; a validação de internações foi extraída para a função
  `converter` em `loader/sih.py` para poder ser testada sem banco.
- **O que foi pedido:** testes para as partes mais frágeis do loader.
- **O que foi aproveitado:** os 11 testes. Eles cobrem o leitor de DBF (inclusive
  o cabeçalho com `0x00` do CNES-ST e registros apagados), o parser de `.cnv`
  (com o caso que causou o erro de região), a interpretação dos nomes de
  arquivo, um registro de internação válido, longa permanência com data antiga,
  oito motivos de rejeição e a remoção de NASC/CEP dos registros rejeitados.
- **Como foi verificado:** `python -m unittest` no `python:3.11-slim` e dentro
  da imagem do loader (`docker compose run --rm loader python -m unittest`):
  11 testes, todos passando. Os casos de teste usam valores observados nos
  arquivos reais (CID N18.5, `DT_INTER` de 2008, `DIAG_SECUN` "0000").
- **Quem revisou:** Cairo Florenço.

### 2026-10-07 — Consultas de caracterização da carga e de histórico da origem

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5), extensão do VS Code.
- **Onde:** `sql/caracterizacao/` (volume, escrita, represamento, consultas de
  leitura L1–L6 e `executar.sh`) e `sql/historico/` (consultas H1–H4 e
  `executar.sh`), com os resultados de 2026-10-07 em `resultados/`.
- **O que foi pedido:** consultas que medem volume, escrita, leitura e defasagem da origem. 
  E também, consultas que só são possíveis porque a origem guarda histórico.
- **O que foi aproveitado:** todas as consultas e os dois scripts. As consultas
  de leitura foram escolhidas pelo assistente a partir das perguntas que a
  plataforma deve responder (pontual por hospital, leitos por região, causas,
  ocupação semanal, permanência e custo, internação fora da UF). Duas correções
  foram feitas depois da primeira execução: a L4 cortava a última semana de
  2024 (que entra em 2025) e misturava a região "Central" de GO com a "Central"
  do DF; a H1 tinha um erro de SQL (`ORDER BY` com apelido de coluna dentro de
  expressão).
- **Como foi verificado:** os dois scripts rodaram sobre a carga completa
  (3,67 milhões de internações) e os resultados foram conferidos contra números
  já conhecidos. As contagens por fonte batem com a tabela `carga`, e o
  represamento medido na H3 (76,5% das saídas de jan/2025 do DF conhecidas na
  primeira competência) é coerente com o da `03_represamento` (65% no mesmo
  mês, 99,5% em até 3 meses). Os tempos vêm de `EXPLAIN (ANALYZE, BUFFERS)`,
  3 execuções por consulta, com máquina e configuração do PostgreSQL gravadas
  no cabeçalho do resultado.
  **Ressalvas que o texto da E1 precisa carregar:** a ocupação semanal da L4 é
  uma estimativa bruta (leito cadastrado não é leito operando, internação de
  zero dia não conta paciente-dia, hospitais de referência distrital caem na
  Região Central); na H2, 2021 é ano de pandemia e infla o crescimento das
  internações; na H4, parte das versões de cadastro é ruído da própria fonte
  (799 versões numa só competência, 12/2022, e 38 estabelecimentos com
  cadastro que vai e volta).
- **Quem revisou:** Cairo Florenço.

### 2026-10-13 — Verificações de qualidade dos dados carregados

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5), extensão do VS Code.
- **Onde:** `loader/qualidade.py`, `loader/__main__.py`,
  `tests/test_qualidade.py`, `docs/e1/03-carga-reprodutivel.md` e `README.md`
  (commit `fb8af72`).
- **O que foi pedido:** verificações sobre os dados já carregados, para
  fortalecer o critério de qualidade e testes de dados.
- **O que foi aproveitado:** as 13 verificações (6 de erro, 7 de alerta) e a
  integração no fim do loader, que termina com código 1 se houver erro. As
  regras foram escolhidas depois de medir cada uma sobre a carga completa, para
  separar o que é erro de carga do que é característica da fonte. O aviso de
  "hospital do DF sem região" que ficava no resumo do loader virou a
  verificação Q06. A primeira versão da Q10 levava 2 min 18 s; foi reescrita
  (agregação por hospital e mês antes do cruzamento) e passou a menos de 1 s.
- **Como foi verificado:** sobre a carga completa, 12 verificações sem
  violação e 1 alerta esperado (7.253 internações com valor zero), em 12 s.
  Num ambiente limpo com a amostra, `docker compose up` rodou as verificações
  e o loader terminou com código 0. Com uma carga marcada como falhou inserida
  de propósito num banco descartável, a Q01 acusou o erro e o comando terminou
  com código 1. Três testes novos protegem a lista de verificações (14 testes
  no total, todos passando).
- **Quem revisou:** Cairo Florenço.

### 2026-10-13 — Remoção de nomes do tema antigo na configuração

- **Ferramenta:** Claude Code (modelo Claude Opus 5.5), extensão do VS Code.
- **Onde:** `pyproject.toml`, `alembic.ini`, `.github/workflows/pages.yml`,
  `.gitignore` (commit `a0f3dbf`); troca do repositório oficial para
  `Luckx98/GuiaTCC-UnB` nos links de README, docs e `mkdocs.yml` (depois
  renomeado para `Luckx98/Leitos-SUS-DF`).
- **O que foi pedido:** tirar da configuração os restos do tema
  GuiaOrientador/CAPES e atualizar o endereço do repositório depois da troca
  de dono.
- **O que foi aproveitado:** tudo. O `pyproject.toml` passou a declarar Python
  3.11, alinhado com a imagem Docker; o workflow do Pages deixou de publicar a
  partir da branch antiga `entrega-1`.
- **Como foi verificado:** migração rodada no banco existente (nada a aplicar),
  14 testes passando, `pyproject.toml` e workflow lidos sem erro pelos
  leitores de TOML e YAML, e busca pelos termos do tema antigo sem ocorrências
  fora do nome do repositório.
- **Quem revisou:** Cairo Florenço.

### 2026-10-19 — Correção de `lakehouse/reconciliar.py` 

- **Ferramenta:** Claude Code (modelo Claude Opus 5), extensão do VS Code.
- **Onde:** `lakehouse/reconciliar.py` (commit `96073e7`).
- **O que foi pedido:** a reconciliação final de `scripts/medir_ingestao.sh`
  travava sobre a carga completa (3,67 milhões de internações); corrigir e
  validar na mesma escala.
- **O que foi aproveitado:** a reescrita completa da função que contava e
  deduplicava as chaves. A versão antiga convertia as colunas de chave em
  `set()`/`Counter()` do Python — 3,67 milhões de tuplas, a causa provável da
  travada. A nova registra o Arrow da varredura no DuckDB e agrega lá (`count`,
  `count(DISTINCT (chave))`, `avg(epoch(...))` para a latência), sem nenhuma
  chave virando objeto Python.
- **Como foi verificado:** em ambiente isolado (cópia da pasta,
  `COMPOSE_PROJECT_NAME` próprio, portas trocadas), primeiro com a amostra (5
  tabelas × 2 caminhos, ok), depois com a carga completa DF+GO 2021→08/2026
  (3.734.853 internações): a reconciliação rodou em 8 s com pico de 83 MB,
  contra a travada de antes. Um erro de rede transitório do SeaweedFS durante
  a exportação do lote causou uma divergência real nessa rodada — o
  `reconciliar` apontou `DIVERGE` corretamente em vez de travar; refeito o
  lote, a reconciliação ficou limpa. Os 35 testes do loader e do lakehouse
  continuam passando.
- **Quem revisou:** Cairo Florenço.

### 2026-10-19 — ADR 0002, mecanismo de ingestão e Iceberg × Delta 

- **Ferramenta:** Claude Code (modelo Claude Opus 5), extensão do VS Code.
- **Onde:** `docker-compose.yml` (`mem_limit` do `cdc`), `lakehouse/cdc.py`
  (filtro de `chaves_ja_gravadas`), `docs/adr/0002-lote-incremental-e-cdc-sobre-iceberg.md`,
  `mkdocs.yml`, `medicoes/e2/iceberg_delta_2026-10-19.txt`,
  `medicoes/e2/semantica_2026-10-19.txt` (commit `31efe6a`).
- **O que foi pedido:** tentar reduzir a memória do consumidor de CDC durante o
  snapshot da carga completa (pico medido em 998 MiB de 1.024), rodar o
  experimento Iceberg × Delta e escrever o ADR do mecanismo
  de ingestão.
- **O que foi aproveitado:** o experimento Iceberg × Delta por completo —
  Iceberg ganha por escrita, tamanho, leitura e, decisivamente, por evolução
  de partição (0,01 s só metadado contra 0,42 s reescrevendo a tabela inteira
  no Delta). O ADR 0002, no formato do ADR 0001. O filtro mais estreito em
  `chaves_ja_gravadas` (`In()` nas datas exatas do lote, em vez de um
  intervalo min-máx) foi mantido por ser estritamente igual ou melhor que o
  anterior.
- **O que não foi aproveitado:** reduzir `CDC_LINHAS_POR_LOTE` de 50.000 para
  20.000 não mudou o pico de memória (1.022 de 1.024 MiB) e foi revertido.
  Subir o `mem_limit` do `cdc` para 1.536m também não resolveu — o pico voltou
  a colar no limite novo (1.534,98 MiB), confirmando que o consumidor cresce
  até perto de qualquer limite dado, não um custo fixo. A causa mais provável
  (acúmulo de metadado do Iceberg ao longo de várias dezenas de commits num
  único snapshot) não foi perfilada; ficou documentada como limitação
  conhecida e gatilho de revisão no próprio ADR, em vez de uma correção.
  `snapshot.mode=no_data` do Debezium foi considerado e descartado: o `cdc`
  não espera o `loader` no Compose, então parte do histórico ficaria fora de
  `cdc.*` para sempre, quebrando a demonstração simples do perfil `e2`.
- **Como foi verificado:** quatro rodadas completas em ambiente isolado
  (carga completa DF+GO, cada uma ~11 min de carga + o snapshot do CDC),
  amostrando a memória do container `cdc` a cada 5 s. `docker compose build`
  e os 35 testes passando depois de cada mudança de código.
- **Quem revisou:** Cairo Florenço.
