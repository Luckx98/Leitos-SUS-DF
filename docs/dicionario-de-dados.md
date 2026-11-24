# Dicionário de Dados — Leitos SUS-DF

Este documento descreve todas as estruturas de dados da plataforma **Leitos SUS-DF**, cobrindo desde os arquivos brutos do DATASUS até a camada analítica de consumo e o experimento vetorial.

---

## 1. Visão Geral das Camadas de Dados

```text
[1. Fontes Brutas]         Arquivos .dbc, .dbf, .cnv (DATASUS) e .csv curado (DF)
        │
        ▼
[2. Origem OLTP]           PostgreSQL 16 (schema public) — insert-only, versionado por competência
        │
        ├──► [3a. Lakehouse Lote]  Apache Iceberg v2 (namespace lote.*) — incremental + janela de maturidade
        └──► [3b. Lakehouse CDC]   Apache Iceberg v2 (namespace cdc.*)  — Debezium + Redpanda
                │
                ▼ (a partir de lote.* + referências de public.*)
[4. Transformação dbt]     DuckDB (schemas bronze, staging, intermediate, marts)
        │
        ▼
[5. Camada de Consumo]     PostgreSQL 16 (schema consumo) — Estrela semanal + SLA/Freshness
        │
        ▼
[6. Banco Vetorial]        PostgreSQL 16 + pgvector (schema semantico) — Frases e embeddings (384d)
```

### Convenções Temporais do Projeto

Todo dado transacional de saúde na plataforma distingue três marcos temporais:

| Marco Temporal | Colunas Típicas | Significado no Domínio |
| --- | --- | --- |
| **Data do Evento** | `dt_internacao`, `dt_saida`, `dia`, `semana`, `mes_saida` | Momento real em que o paciente internou, permaneceu ocupando leito ou teve alta/óbito. |
| **Data de Processamento** | `competencia`, `competencia_inicio` | Mês de apresentação/faturamento da AIH no SIH/SUS ou mês do retrato cadastral no CNES (sempre truncado no dia `01` do mês: `AAAA-MM-01`). |
| **Data de Ingestão / Construção** | `dt_ingestao`, `iniciada_em`, `concluida_em`, `_commit_em`, `_ingerido_em`, `construida_em` | Carimbo de tempo (UTC) de gravação técnica na origem, no lakehouse ou na camada de consumo. |

---

## 2. Fontes Brutas e Arquivos de Referência

### 2.1. SIH/SUS — AIH Reduzida (`RD<UF><AAMM>.dbc`)

Origem: `ftp://ftp.datasus.gov.br/dissemin/publicos/SIHSUS/200801_/Dados/` (recorte local em `dados/amostra/RDDF2501.dbc`).

| Campo Original (DBF/DBC) | Tipo Bruto | Coluna de Destino (`public.internacao`) | Tratamento / Regra de Validação no Loader (`loader/sih.py`) |
| --- | --- | --- | --- |
| `ANO_CMPT`, `MES_CMPT` | `CHAR(4)`, `CHAR(2)` | `competencia` | Concatenados (`AAAAMM`) e confrontados com a competência do nome do arquivo; gravado como `DATE` (`AAAA-MM-01`). |
| `N_AIH` | `CHAR(13)` | `n_aih` | Deve obedecer à expressão regular `^[0-9]{13}$`. Único por `(N_AIH, DT_SAIDA)` dentro do mesmo arquivo. |
| `DT_SAIDA` | `CHAR(8)` | `dt_saida` | Convertido de `AAAAMMDD` para `DATE`. Deve satisfazer `DT_SAIDA >= DT_INTER` e ser anterior ao mês seguinte ao da competência. |
| `IDENT` | `CHAR(1)` | `ident` | Tipo da AIH: `'1'` (Principal/Normal), `'3'` (Continuação) ou `'5'` (Longa permanência). Valores fora de `{'1','3','5'}` são rejeitados. |
| `CNES` | `CHAR(7)` | `cnes` | Código CNES do hospital. Deve existir previamente em `public.estabelecimento`. |
| `DT_INTER` | `CHAR(8)` | `dt_internacao` | Convertido de `AAAAMMDD` para `DATE`. Na longa permanência (`IDENT='5'`), reflete a internação original e não o início da fatura mensal. |
| `DIAS_PERM` | `TEXT/NUM` | `dias_permanencia` | Convertido para inteiro (`SMALLINT >= 0`). |
| `QT_DIARIAS` | `TEXT/NUM` | `qt_diarias` | Convertido para inteiro (`SMALLINT >= 0`). |
| `ESPEC` | `CHAR(2)` | `especialidade` | Código da especialidade do leito na AIH. Obrigatório. |
| `CAR_INT` | `CHAR(2)` | `carater_internacao` | Caráter da internação (ex.: eletiva, urgência). Vazio vira `NULL`. |
| `COMPLEX` | `CHAR(2)` | `complexidade` | Complexidade do atendimento. Vazio vira `NULL`. |
| `DIAG_PRINC` | `VARCHAR(4)` | `cid_principal` | Código CID-10 principal. Deve existir em `public.cid`. |
| `DIAG_SECUN` | `VARCHAR(4)` | `cid_secundario` | Código CID-10 secundário. `""` ou `"0000"` viram `NULL`. |
| `PROC_REA` | `CHAR(10)` | `procedimento` | Procedimento realizado (SIGTAP). Deve obedecer a `^[0-9]{10}$`. |
| `UTI_MES_TO` | `TEXT/NUM` | `dias_uti` | Total de diárias de UTI no mês (`SMALLINT >= 0`). |
| `MARCA_UTI` | `CHAR(2)` | `marca_uti` | Tipo de UTI utilizada. Vazio vira `NULL`. |
| `VAL_TOT` | `TEXT/DEC` | `valor_total` | Valor total aprovado na AIH (`NUMERIC(12,2) >= 0`). |
| `VAL_UTI` | `TEXT/DEC` | `valor_uti` | Valor de UTI aprovado na AIH (`NUMERIC(12,2) >= 0`). |
| `IDADE` | `TEXT/NUM` | `idade` | Valor numérico da idade na unidade indicada por `COD_IDADE` (`SMALLINT >= 0`). |
| `COD_IDADE` | `CHAR(1)` | `cod_idade` | Unidade da idade (`'2'`=dias, `'3'`=meses, `'4'`=anos, `'5'`=centena de anos). |
| `SEXO` | `CHAR(1)` | `sexo` | Sexo do paciente (`'1'`=Masculino, `'3'`/`'2'`=Feminino, `'0'`/`'9'`=Ignorado). |
| `RACA_COR` | `CHAR(2)` | `raca_cor` | Raça/cor declarada. Vazio vira `NULL`. |
| `MUNIC_RES` | `CHAR(6)` | `municipio_residencia` | Código IBGE (6 dígitos) do município de residência. Deve existir em `public.municipio`. |
| `MUNIC_MOV` | `CHAR(6)` | `municipio_estabelecimento` | Código IBGE (6 dígitos) do município do estabelecimento. Deve existir em `public.municipio`. |
| `MORTE` | `CHAR(1)` | `obito` | `'1'` → `TRUE`, `'0'` → `FALSE`. Outros valores rejeitam a linha. |
| `GESTAO` | `CHAR(1)` | `tipo_gestao` | Tipo de gestão na AIH. Vazio vira `NULL`. |
| `NASC`, `CEP`, `CPF_AUT`, `GESTOR_CPF`, `INSC_PN` | — | *(Descartados)* | **Minimização LGPD (art. 5º, II):** removidos antes da gravação tanto na tabela principal quanto em `carga_rejeicao`. |

### 2.2. CNES — Estabelecimentos (`ST<UF><AAMM>.dbc`)

Origem: `ftp://ftp.datasus.gov.br/dissemin/publicos/CNES/200508_/Dados/ST/` (amostra em `dados/amostra/STDF2501.dbc`).

| Campo Original | Tipo Bruto | Coluna de Destino (`estabelecimento_versao`) | Tratamento / Regra de Validação (`loader/cnes.py`) |
| --- | --- | --- | --- |
| `CNES` | `CHAR(7)` | `cnes` | Regex `^[0-9]{7}$`. Único por arquivo. Insere em `estabelecimento` na primeira aparição. |
| `COMPETEN` | `CHAR(6)` | `competencia_inicio` | Validado contra a competência do arquivo (`AAAAMM`). Gravado como `DATE` (`AAAA-MM-01`). |
| `CODUFMUN` | `CHAR(6)` | `cod_municipio` | Código IBGE de 6 dígitos; validado contra `public.municipio`. |
| `TP_UNID` | `CHAR(2)` | `tipo_unidade` | Código do tipo de unidade no CNES (obrigatório). |
| `TPGESTAO` | `CHAR(1)` | `tipo_gestao` | `'E'` (Estadual), `'M'` (Municipal), `'D'` (Dupla), `'S'` (Sem gestão), `'F'`/`'Z'` (legados). Obrigatório. |
| `NAT_JUR` | `CHAR(4)` | `natureza_juridica` | Código CONCLA de natureza jurídica. Vazio vira `NULL`. |
| `CNPJ_MAN` | `CHAR(14)` | `cnpj_mantenedora` | CNPJ da entidade mantenedora. Vazio ou `'00000000000000'` vira `NULL`. |
| `VINC_SUS` | `CHAR(1)` | `vinculo_sus` | `'1'` → `TRUE`, `'0'` → `FALSE`, outros → `NULL`. |
| `ATENDHOS` | `CHAR(1)` | `atende_internacao` | `'1'` → `TRUE`, `'0'` → `FALSE`, outros → `NULL`. |
| `URGEMERG` | `CHAR(1)` | `atende_urgencia` | `'1'` → `TRUE`, `'0'` → `FALSE`, outros → `NULL`. |

### 2.3. CNES — Leitos (`LT<UF><AAMM>.dbc`)

Origem: `ftp://ftp.datasus.gov.br/dissemin/publicos/CNES/200508_/Dados/LT/` (amostra em `dados/amostra/LTDF2501.dbc`).

| Campo Original | Tipo Bruto | Coluna de Destino (`public.leito`) | Tratamento / Regra de Validação (`loader/cnes.py`) |
| --- | --- | --- | --- |
| `COMPETEN` | `CHAR(6)` | `competencia` | Validado contra a competência do arquivo (`AAAAMM`). Gravado como `DATE` (`AAAA-MM-01`). |
| `CNES` | `CHAR(7)` | `cnes` | Deve existir em `public.estabelecimento` (ST é carregado antes de LT). |
| `CODLEITO` | `CHAR(2)` | `cod_leito` | Especialidade do leito (`^[0-9]{2}$`). Único por `(CNES, CODLEITO)` no arquivo. |
| `TP_LEITO` | `CHAR(1)` | `tipo_leito` | Grupo do leito (`^[0-9]$`, ex.: cirúrgico, clínico, complementar/UTI, obstétrico, pediátrico). |
| `QT_EXIST` | `TEXT/NUM` | `qt_existente` | Quantidade de leitos existentes (`SMALLINT >= 0`). |
| `QT_CONTR` | `TEXT/NUM` | `qt_contratado` | Quantidade de leitos contratados (`SMALLINT >= 0`). |
| `QT_SUS` | `TEXT/NUM` | `qt_sus` | Quantidade de leitos disponibilizados ao SUS (`SMALLINT >= 0`). Denominador da taxa de ocupação. |
| `QT_NSUS` | `TEXT/NUM` | `qt_nao_sus` | Quantidade de leitos não SUS (`SMALLINT >= 0`). |

### 2.4. Tabelas Auxiliares (`TAB_SIH.zip` e CSV Curado do DF)

| Arquivo / Membro | Destino no Banco | Campos Extraídos e Regras (`loader/referencias.py`) |
| --- | --- | --- |
| `CNV/br_regsaud.cnv` (`TAB_SIH.zip`) | `public.regiao_saude` | Extrai código de 5 dígitos (`cod_regiao_saude`), rótulo textual (`nome`), prefixo de 2 dígitos (`cod_uf`) e o mapeamento município → região de saúde. |
| `CNV/br_municip.cnv` (`TAB_SIH.zip`) | `public.municipio` | Extrai código IBGE de 6 dígitos (`cod_municipio`), nome do município (`nome`), `cod_uf` (`cod_municipio[:2]`) e associa `cod_regiao_saude` lido de `br_regsaud.cnv`. |
| `DBF/cid10.dbf` (`TAB_SIH.zip`) | `public.cid` | `CD_COD` (sem ponto, em maiúsculas, validado por `^[A-Z][0-9]{2}[0-9X]?$`) → `cod_cid`; `CD_DESCR` (removido o código inicial repetido) → `descricao`. |
| `dados/referencia/estabelecimento_regiao_saude_df.csv` | `public.estabelecimento_regiao_df` | Colunas do CSV: `cnes`, `nome_fantasia`, `bairro_cnes` (apenas no CSV), `regiao_administrativa`, `cod_regiao_saude`, `regiao_saude` (apenas no CSV), `observacao`. |

---

## 3. Camada de Origem OLTP (`PostgreSQL 16`, schema `public`)

Todas as tabelas de dados e de controle de carga na origem são **insert-only**, protegidas pela trigger `bloquear_alteracao()` (`BEFORE UPDATE OR DELETE`), que aborta qualquer tentativa de mutação ou exclusão.

### 3.1. `public.carga`

Controla a auditoria e a idempotência por arquivo carregado (migração `0001`).

| Coluna | Tipo SQL | Nulo? | Chave / Restrição | Descrição |
| --- | --- | --- | --- | --- |
| `id_carga` | `BIGINT` | Não | `PRIMARY KEY` (`GENERATED ALWAYS AS IDENTITY`) | Identificador sequencial único da transação de carga. Usado como marca d'água pelo lote incremental. |
| `fonte` | `TEXT` | Não | `CHECK (fonte IN ('SIH_RD', 'CNES_ST', 'CNES_LT', 'REFERENCIA'))` | Tipo de fonte de dados do arquivo processado. |
| `arquivo` | `TEXT` | Não | Parte de `uq_carga_arquivo_concluida` | Nome base do arquivo carregado (ex.: `RDDF2501.dbc`). |
| `uf` | `CHAR(2)` | Sim | Indexado em `idx_carga_fonte_competencia` | Sigla da UF do arquivo (`'DF'`, `'GO'`, ou `NULL` para referências). |
| `competencia` | `DATE` | Sim | `CHECK (competencia = date_trunc('month', competencia))` | Primeiro dia do mês de competência do arquivo (`AAAA-MM-01`), ou `NULL` para referências. |
| `sha256` | `CHAR(64)` | Não | Parte de `uq_carga_arquivo_concluida` | Hash SHA-256 em hexadecimal do conteúdo bruto do arquivo. Garante idempotência. |
| `tamanho_bytes` | `BIGINT` | Não | `CHECK (tamanho_bytes >= 0)` | Tamanho do arquivo bruto em bytes. |
| `linhas_lidas` | `INTEGER` | Não | `DEFAULT 0 CHECK (linhas_lidas >= 0)` | Total de registros lidos do arquivo bruto. |
| `linhas_inseridas` | `INTEGER` | Não | `DEFAULT 0 CHECK (linhas_inseridas >= 0)` | Total de registros efetivamente gravados no banco. |
| `linhas_rejeitadas` | `INTEGER` | Não | `DEFAULT 0 CHECK (linhas_rejeitadas >= 0)` | Total de registros recusados na validação e gravados em `carga_rejeicao`. |
| `iniciada_em` | `TIMESTAMPTZ` | Não | — | Carimbo de tempo de início do processamento do arquivo. |
| `concluida_em` | `TIMESTAMPTZ` | Não | `DEFAULT clock_timestamp()`, `CHECK (concluida_em >= iniciada_em)` | Carimbo de tempo de término da carga. |
| `status` | `TEXT` | Não | `CHECK (status IN ('concluida', 'falhou'))` | Resultado final da execução da carga. |
| `mensagem` | `TEXT` | Sim | — | Mensagem de erro em caso de falha (`status = 'falhou'`). |

- **Índices:**
  - `uq_carga_arquivo_concluida`: `UNIQUE (fonte, arquivo, sha256) WHERE status = 'concluida'`
  - `idx_carga_fonte_competencia`: `(fonte, uf, competencia)`

### 3.2. `public.carga_rejeicao`

Guarda as linhas recusadas durante a validação, sem dados pessoais sensíveis (migração `0001`).

| Coluna | Tipo SQL | Nulo? | Chave / Restrição | Descrição |
| --- | --- | --- | --- | --- |
| `id_carga` | `BIGINT` | Não | `PK`, `FK -> carga(id_carga) DEFERRABLE INITIALLY DEFERRED` | Carga em que o registro foi rejeitado. |
| `linha` | `INTEGER` | Não | `PK`, `CHECK (linha > 0)` | Número da linha (base 1) no arquivo de origem. |
| `motivo` | `TEXT` | Não | — | Regra de validação violada (ex.: `"CNES sem cadastro"`, `"DT_SAIDA anterior a DT_INTER"`). |
| `registro` | `JSONB` | Não | — | Conteúdo bruto do registro serializado em JSON (expurgado de campos LGPD no SIH). |

### 3.3. `public.regiao_saude`

Regiões de saúde oficiais do DATASUS (migração `0002`).

| Coluna | Tipo SQL | Nulo? | Chave / Restrição | Descrição |
| --- | --- | --- | --- | --- |
| `cod_regiao_saude` | `CHAR(5)` | Não | `PRIMARY KEY`, `CHECK (cod_regiao_saude ~ '^[0-9]{5}$')` | Código de 5 dígitos da região de saúde no DATASUS (ex.: `'53006'` para Central/DF). |
| `nome` | `TEXT` | Não | — | Nome oficial da região de saúde. |
| `cod_uf` | `CHAR(2)` | Não | — | Código IBGE de 2 dígitos da Unidade da Federação (`'53'` = DF, `'52'` = GO). |

### 3.4. `public.municipio`

Municípios brasileiros com vínculo para região de saúde (migração `0002`).

| Coluna | Tipo SQL | Nulo? | Chave / Restrição | Descrição |
| --- | --- | --- | --- | --- |
| `cod_municipio` | `CHAR(6)` | Não | `PRIMARY KEY`, `CHECK (cod_municipio ~ '^[0-9]{6}$')` | Código IBGE do município com 6 dígitos (padrão DATASUS, sem dígito verificador). |
| `nome` | `TEXT` | Não | — | Nome do município. |
| `cod_uf` | `CHAR(2)` | Não | — | Código IBGE de 2 dígitos da UF. |
| `cod_regiao_saude` | `CHAR(5)` | Sim | `FK -> regiao_saude(cod_regiao_saude)`, indexado | Região de saúde do município (em Brasília `530010` é `NULL` na tabela geral e resolvido por hospital em `estabelecimento_regiao_df`). |

### 3.5. `public.cid`

Subcategorias e categorias da Classificação Internacional de Doenças — CID-10 (migração `0002`).

| Coluna | Tipo SQL | Nulo? | Chave / Restrição | Descrição |
| --- | --- | --- | --- | --- |
| `cod_cid` | `VARCHAR(4)` | Não | `PRIMARY KEY`, `CHECK (cod_cid ~ '^[A-Z][0-9]{2}[0-9X]?$')` | Código da CID-10 sem ponto (3 ou 4 caracteres, ex.: `'J189'`, `'A90'`). |
| `descricao` | `TEXT` | Não | — | Descrição clínica da doença ou agravo. |

### 3.6. `public.estabelecimento_regiao_df`

Tabela curada pela equipe para mapear cada hospital do DF (`cod_municipio = '530010'`) à sua Região de Saúde da SES-DF (migração `0002`).

| Coluna | Tipo SQL | Nulo? | Chave / Restrição | Descrição |
| --- | --- | --- | --- | --- |
| `cnes` | `CHAR(7)` | Não | `PRIMARY KEY`, `CHECK (cnes ~ '^[0-9]{7}$')` | Código CNES do estabelecimento de saúde no Distrito Federal. |
| `nome_fantasia` | `TEXT` | Não | — | Nome fantasia do hospital/estabelecimento. |
| `regiao_administrativa` | `TEXT` | Não | — | Região Administrativa (RA) do DF onde o hospital se localiza. |
| `cod_regiao_saude` | `CHAR(5)` | Não | `FK -> regiao_saude(cod_regiao_saude)` | Código da região de saúde do DF (`53002` a `53008`). |
| `observacao` | `TEXT` | Sim | — | Notas de curadoria (ex.: hospital de campanha temporário da pandemia). |

### 3.7. `public.estabelecimento`

Catálogo de chaves de negócio dos estabelecimentos de saúde (migração `0003`).

| Coluna | Tipo SQL | Nulo? | Chave / Restrição | Descrição |
| --- | --- | --- | --- | --- |
| `cnes` | `CHAR(7)` | Não | `PRIMARY KEY`, `CHECK (cnes ~ '^[0-9]{7}$')` | Código Nacional de Estabelecimento de Saúde (7 dígitos). |
| `primeira_carga` | `BIGINT` | Não | `FK -> carga(id_carga) DEFERRABLE INITIALLY DEFERRED` | Identificador da carga em que o CNES foi visto pela primeira vez. |
| `dt_ingestao` | `TIMESTAMPTZ` | Não | `DEFAULT now()` | Carimbo de tempo de inserção do CNES. |

### 3.8. `public.estabelecimento_versao`

Histórico cadastral dos estabelecimentos (SCD Tipo 2 na origem: uma nova linha só é gravada quando algum atributo monitorado muda ou quando uma competência anterior à primeira versão conhecida é carregada) (migração `0003`).

| Coluna | Tipo SQL | Nulo? | Chave / Restrição | Descrição |
| --- | --- | --- | --- | --- |
| `cnes` | `CHAR(7)` | Não | `PK`, `FK -> estabelecimento(cnes)` | Código CNES do estabelecimento. |
| `competencia_inicio` | `DATE` | Não | `PK`, `CHECK (competencia_inicio = date_trunc('month', competencia_inicio))` | Competência (`AAAA-MM-01`) em que esta configuração cadastral passou a vigorar. |
| `cod_municipio` | `CHAR(6)` | Não | `FK -> municipio(cod_municipio)`, indexado | Município de localização do estabelecimento na versão. |
| `tipo_unidade` | `CHAR(2)` | Não | — | Código do tipo de estabelecimento no CNES (ex.: `'05'` Hospital Geral, `'07'` Hospital Especializado). |
| `tipo_gestao` | `CHAR(1)` | Não | — | Esfera de gestão do SUS: `'E'` (Estadual), `'M'` (Municipal), `'D'` (Dupla), `'S'` (Sem gestão). |
| `natureza_juridica` | `CHAR(4)` | Sim | — | Código CONCLA de natureza jurídica (administração pública, privada, filantrópica etc.). |
| `cnpj_mantenedora` | `CHAR(14)` | Sim | — | CNPJ da mantenedora (14 dígitos numéricos), quando aplicável. |
| `vinculo_sus` | `BOOLEAN` | Sim | — | Indica se o estabelecimento possui vínculo ativo com o SUS. |
| `atende_internacao` | `BOOLEAN` | Sim | — | Indica se o estabelecimento realiza atendimento hospitalar de internação. |
| `atende_urgencia` | `BOOLEAN` | Sim | — | Indica se o estabelecimento possui atendimento de urgência/emergência. |
| `id_carga` | `BIGINT` | Não | `FK -> carga(id_carga) DEFERRABLE INITIALLY DEFERRED` | Carga que inseriu a versão. |
| `dt_ingestao` | `TIMESTAMPTZ` | Não | `DEFAULT now()` | Carimbo de tempo de gravação na origem. |

### 3.9. `public.leito`

Retrato mensal da capacidade física e contratual de leitos por estabelecimento e especialidade (migração `0004`).

| Coluna | Tipo SQL | Nulo? | Chave / Restrição | Descrição |
| --- | --- | --- | --- | --- |
| `competencia` | `DATE` | Não | `PK`, `CHECK (competencia = date_trunc('month', competencia))` | Mês de referência do cadastro de leitos (`AAAA-MM-01`). |
| `cnes` | `CHAR(7)` | Não | `PK`, `FK -> estabelecimento(cnes)` | Código CNES do estabelecimento. |
| `cod_leito` | `CHAR(2)` | Não | `PK`, `CHECK (cod_leito ~ '^[0-9]{2}$')` | Código da especialidade do leito no CNES. |
| `tipo_leito` | `CHAR(1)` | Não | `CHECK (tipo_leito ~ '^[0-9]$')` | Código do grupo/tipo de leito no CNES. |
| `qt_existente` | `SMALLINT` | Não | `CHECK (qt_existente >= 0)` | Quantidade total de leitos instalados/existentes. |
| `qt_contratado` | `SMALLINT` | Não | `CHECK (qt_contratado >= 0)` | Quantidade de leitos contratados. |
| `qt_sus` | `SMALLINT` | Não | `CHECK (qt_sus >= 0)` | Quantidade de leitos disponíveis para o SUS. |
| `qt_nao_sus` | `SMALLINT` | Não | `CHECK (qt_nao_sus >= 0)` | Quantidade de leitos privados/não SUS. |
| `id_carga` | `BIGINT` | Não | `PK`, `FK -> carga(id_carga) DEFERRABLE INITIALLY DEFERRED` | Carga que trouxe o registro (permite conviver com republicações do DATASUS). |
| `dt_ingestao` | `TIMESTAMPTZ` | Não | `DEFAULT now()` | Carimbo de tempo de gravação na origem. |

- **Índices:** `idx_leito_cnes (cnes, competencia)`, `idx_leito_carga (id_carga)`.

### 3.10. `public.internacao`

Registros de Autorização de Internação Hospitalar (AIH reduzida — SIH/SUS) pagos pelo SUS (migração `0005`).

| Coluna | Tipo SQL | Nulo? | Chave / Restrição | Descrição |
| --- | --- | --- | --- | --- |
| `competencia` | `DATE` | Não | `PK`, `CHECK (competencia = date_trunc('month', competencia))` | Mês de apresentação/processamento contábil da AIH (`AAAA-MM-01`). |
| `n_aih` | `CHAR(13)` | Não | `PK`, `CHECK (n_aih ~ '^[0-9]{13}$')` | Número de 13 dígitos da AIH. |
| `dt_saida` | `DATE` | Não | `PK`, `CHECK (dt_saida >= dt_internacao)` | Data da alta, transferência ou óbito (ou fim do período faturado na longa permanência). |
| `id_carga` | `BIGINT` | Não | `PK`, `FK -> carga(id_carga) DEFERRABLE INITIALLY DEFERRED` | Identificador da carga que inseriu a linha. |
| `ident` | `CHAR(1)` | Não | `CHECK (ident IN ('1', '3', '5'))` | Identificador do tipo de AIH (`'1'`=normal, `'3'`=continuação, `'5'`=longa permanência). |
| `cnes` | `CHAR(7)` | Não | `FK -> estabelecimento(cnes)` | Código CNES do hospital onde ocorreu a internação. |
| `dt_internacao` | `DATE` | Não | `CHECK (dt_saida >= dt_internacao)` | Data de início da internação. |
| `dias_permanencia` | `SMALLINT` | Não | `CHECK (dias_permanencia >= 0)` | Dias de permanência cobrados na AIH. Usado para expandir os paciente-dias. |
| `qt_diarias` | `SMALLINT` | Não | `CHECK (qt_diarias >= 0)` | Quantidade de diárias pagas na AIH. |
| `especialidade` | `CHAR(2)` | Não | — | Especialidade do leito da internação. |
| `carater_internacao` | `CHAR(2)` | Sim | — | Caráter do atendimento (eletivo, urgência, acidente etc.). |
| `complexidade` | `CHAR(2)` | Sim | — | Nível de complexidade do procedimento (média, alta). |
| `cid_principal` | `VARCHAR(4)` | Não | `FK -> cid(cod_cid)` | Diagnóstico principal da internação (CID-10). |
| `cid_secundario` | `VARCHAR(4)` | Sim | — | Diagnóstico secundário da internação (CID-10), quando informado. |
| `procedimento` | `CHAR(10)` | Não | `CHECK (procedimento ~ '^[0-9]{10}$')` | Código de 10 dígitos do procedimento principal realizado. |
| `dias_uti` | `SMALLINT` | Não | `CHECK (dias_uti >= 0)` | Quantidade de diárias em Unidade de Terapia Intensiva. |
| `marca_uti` | `CHAR(2)` | Sim | — | Tipo de UTI utilizada. |
| `valor_total` | `NUMERIC(12,2)` | Não | `CHECK (valor_total >= 0)` | Valor financeiro total aprovado para a AIH (em R$). |
| `valor_uti` | `NUMERIC(12,2)` | Não | `CHECK (valor_uti >= 0)` | Parcela do valor aprovada para diárias de UTI (em R$). |
| `idade` | `SMALLINT` | Não | `CHECK (idade >= 0)` | Valor numérico da idade do paciente na unidade `cod_idade`. |
| `cod_idade` | `CHAR(1)` | Não | — | Unidade de medida da idade (`'2'`=dias, `'3'`=meses, `'4'`=anos, `'5'`=centena de anos). |
| `sexo` | `CHAR(1)` | Não | — | Código do sexo do paciente. |
| `raca_cor` | `CHAR(2)` | Sim | — | Código de raça/cor do paciente. |
| `municipio_residencia` | `CHAR(6)` | Não | `FK -> municipio(cod_municipio)` | Município de residência do paciente (permite medir fluxo do Entorno/GO para o DF). |
| `municipio_estabelecimento` | `CHAR(6)` | Não | `FK -> municipio(cod_municipio)` | Município onde se situa o hospital da internação. |
| `obito` | `BOOLEAN` | Não | — | Indica se a saída ocorreu por óbito (`TRUE`) ou não (`FALSE`). |
| `tipo_gestao` | `CHAR(1)` | Sim | — | Esfera de gestão informada na AIH. |
| `dt_ingestao` | `TIMESTAMPTZ` | Não | `DEFAULT now()` | Carimbo de tempo de inserção no PostgreSQL. |

- **Índices:** `idx_internacao_carga (id_carga)`, `idx_internacao_cnes_saida (cnes, dt_saida)`, `idx_internacao_dt_internacao (dt_internacao)`, `idx_internacao_cid (cid_principal)`, `idx_internacao_n_aih (n_aih)`.

### 3.11. Visões da Origem (`public.*_vigente` e `estabelecimento_vigencia`)

Criadas nas migrações `0003` e `0006` para resolver a vigência temporal e deduplicar eventuais republicações de arquivos pelo DATASUS:

| Visão | Definição / Regra de Negócio | Colunas Adicionais / Comportamento |
| --- | --- | --- |
| `public.estabelecimento_vigencia` | `SELECT v.*, lead(v.competencia_inicio) OVER (PARTITION BY v.cnes ORDER BY v.competencia_inicio) AS competencia_fim FROM estabelecimento_versao v` | Acrescenta `competencia_fim` (`DATE`, exclusiva; `NULL` na versão atual) a todas as colunas de `estabelecimento_versao`. |
| `public.carga_vigente` | `SELECT DISTINCT ON (fonte, uf, competencia) * FROM carga WHERE status = 'concluida' AND competencia IS NOT NULL ORDER BY fonte, uf, competencia, id_carga DESC` | Seleciona apenas a última carga bem-sucedida de cada `(fonte, uf, competencia)`. |
| `public.leito_vigente` | `SELECT l.* FROM leito l JOIN carga_vigente c USING (id_carga)` | Filtra `public.leito` mantendo somente os registros da carga vigente de cada competência. |
| `public.internacao_vigente` | `SELECT i.* FROM internacao i JOIN carga_vigente c USING (id_carga)` | Filtra `public.internacao` mantendo somente os registros da carga vigente de cada competência. |

---

## 4. Camada Lakehouse (`Apache Iceberg v2` sobre `SeaweedFS S3`)

O catálogo Iceberg é persistido no banco PostgreSQL `iceberg` e os dados residem no bucket `s3://lakehouse/` em arquivos Parquet comprimidos com **Zstandard (`zstd`)** (`lakehouse/esquemas.py`). Os arquivos originais baixados do DATASUS são arquivados em `s3://brutos/`.

### 4.1. Tabelas Espelhadas nos Namespaces `lote.*` e `cdc.*`

As cinco tabelas publicadas na replicação lógica (`carga`, `estabelecimento`, `estabelecimento_versao`, `leito`, `internacao`) existem com esquema idêntico tanto em `lote.<tabela>` quanto em `cdc.<tabela>`:

- **Conversão de tipos para Iceberg:**
  - `CHAR(n)`, `VARCHAR(n)` e `TEXT` → `StringType`
  - `SMALLINT` e `INTEGER` → `IntegerType`
  - `BIGINT` → `LongType`
  - `NUMERIC(12,2)` → `DecimalType(12, 2)`
  - `BOOLEAN` → `BooleanType`
  - `DATE` → `DateType`
  - `TIMESTAMPTZ` → `TimestamptzType`
- **Particionamento oculto (Hidden Partitioning):**
  - `lote.internacao` e `cdc.internacao` são particionadas por `YearTransform(dt_saida)` (campo de partição `dt_saida_ano`).
  - As demais tabelas (`carga`, `estabelecimento`, `estabelecimento_versao`, `leito`) não possuem particionamento devido ao volume reduzido (~2 MB em Parquet).

#### Colunas de Controle Acrescentadas a Todas as Tabelas Iceberg (`lote.*` e `cdc.*`)

| Coluna | Tipo Iceberg | Preenchimento em `lote.*` | Preenchimento em `cdc.*` | Significado |
| --- | --- | --- | --- | --- |
| `_op` | `StringType` | Constante `'c'` | `'r'` (snapshot inicial) ou `'c'` (insert via WAL) | Operação capturada na origem. |
| `_lsn` | `LongType` | `NULL` | LSN (`source.lsn`) do WAL do PostgreSQL | Posição exata no log de transação da origem. |
| `_commit_em` | `TimestamptzType` | `carga.concluida_em` | `source.ts_ms` do evento Debezium | Instante do commit da transação no PostgreSQL. |
| `_ingerido_em` | `TimestamptzType` | Timestamp UTC da exportação do lote | Timestamp UTC da gravação do micro-lote CDC | Instante em que a linha foi comitada no snapshot Iceberg (`_ingerido_em - _commit_em` = latência de ingestão). |

#### Propriedades Customizadas nos Snapshots Iceberg

| Propriedade | Namespace | Descrição |
| --- | --- | --- |
| `lote.id_carga_max` | `lote.*` | Marca d'água (`id_carga` máximo exportado da origem) gravada atomicamente junto com os dados no commit do snapshot. |
| `janela.inicio` | `lote.internacao` | Data inicial (`AAAA-MM-01`) da janela de dado atrasado reprocessada atomicamente (`delete` + `append`). |
| `cdc.offset.leitos.public.<tabela>` | `cdc.*` | Próximo offset do tópico Redpanda a ser lido após o commit do snapshot; garante retomada exata (*effectively-once* combinado com deduplicação pela PK). |

### 4.2. `lote.maturidade`

Tabela exclusiva do namespace `lote`, recalculada a cada reprocessamento da janela de dado atrasado (`lakehouse/janela.py`). Classifica se um mês de alta hospitalar já recebeu competências posteriores suficientes (mínimo de 3 meses, que cobrem 99,5% do represamento medido na E1).

| Field ID | Coluna | Tipo Iceberg | Descrição |
| --- | --- | --- | --- |
| `1` | `uf` | `StringType` | Sigla da UF do estabelecimento (`'DF'` ou `'GO'`). |
| `2` | `mes_saida` | `DateType` | Mês da data de saída do paciente (`AAAA-MM-01`). |
| `3` | `internacoes` | `LongType` | Quantidade de AIHs com alta naquele `mes_saida` presentes no lakehouse até o momento. |
| `4` | `competencia_referencia` | `DateType` | Maior competência do SIH/SUS carregada para aquela UF (`max(competencia)`). |
| `5` | `meses_observados` | `IntegerType` | Diferença em meses entre `competencia_referencia` e `mes_saida`. |
| `6` | `status` | `StringType` | `'maduro'` quando `meses_observados >= 3`; `'provisório'` quando `meses_observados < 3`. |
| `7` | `calculado_em` | `TimestamptzType` | Instante UTC do cálculo da maturidade. |

---

## 5. Camada de Transformação Analítica (`dbt-duckdb`)

O motor de transformação é o **DuckDB** (`/app/var/analitico.duckdb`), orquestrado pelo projeto dbt em `transformacao/`.

### 5.1. Camada `bronze` (`transformacao/fontes.py`)

Criada antes do `dbt build` para conectar o DuckDB ao catálogo Iceberg e às tabelas de referência da origem:

- **Views sobre `iceberg_scan()` (`lote.*`):** `bronze.carga`, `bronze.estabelecimento_versao`, `bronze.leito`, `bronze.internacao`, `bronze.maturidade`.
- **Tabelas copiadas da origem (`public.*`):** `bronze.municipio`, `bronze.cid`, `bronze.regiao_saude`, `bronze.estabelecimento_regiao_df`.

### 5.2. Camada `staging` (`transformacao/models/staging/`)

Materializada como **views** no schema `staging` do DuckDB. Aplica limpeza de espaços (`trim`), tipagem explícita e filtro de carga vigente:

| Modelo (`staging.*`) | Fonte (`bronze.*`) | Colunas Produzidas | Regra Aplicada |
| --- | --- | --- | --- |
| `stg_carga_vigente` | `bronze.carga` | `id_carga`, `fonte`, `uf`, `competencia`, `status` | Filtra `status = 'concluida'` e `competencia IS NOT NULL`; aplica `QUALIFY row_number() OVER (PARTITION BY fonte, uf, competencia ORDER BY id_carga DESC) = 1`. |
| `stg_cid` | `bronze.cid` | `cod_cid`, `descricao` | `trim(cod_cid)`. |
| `stg_estabelecimento_versao` | `bronze.estabelecimento_versao` | `cnes`, `competencia_inicio`, `cod_municipio`, `tipo_unidade`, `tipo_gestao`, `natureza_juridica`, `cnpj_mantenedora`, `vinculo_sus`, `atende_internacao`, `atende_urgencia` | Deduplica por `(cnes, competencia_inicio)` mantendo o maior `id_carga`. |
| `stg_internacao` | `bronze.internacao` + `stg_carga_vigente` | `competencia`, `n_aih`, `dt_saida`, `id_carga`, `cnes`, `dt_internacao`, `dias_permanencia`, `cid_principal`, `valor_total`, `municipio_residencia`, `_ingerido_em` | Mantém apenas linhas pertencentes à `stg_carga_vigente` da fonte `'SIH_RD'`. |
| `stg_leito` | `bronze.leito` + `stg_carga_vigente` | `competencia`, `cnes`, `cod_leito`, `qt_sus` | Mantém apenas linhas pertencentes à `stg_carga_vigente` da fonte `'CNES_LT'`. |
| `stg_maturidade` | `bronze.maturidade` | `uf`, `mes_saida`, `status` | Normaliza `uf` e converte `mes_saida` para `DATE`. |
| `stg_municipio` | `bronze.municipio` | `cod_municipio`, `nome`, `cod_uf`, `cod_regiao_saude` | `trim` nos códigos; string vazia em `cod_regiao_saude` vira `NULL`. |
| `stg_regiao_df` | `bronze.estabelecimento_regiao_df` | `cnes`, `nome_fantasia`, `cod_regiao_saude` | `trim` em `cnes` e `cod_regiao_saude`. |
| `stg_regiao_saude` | `bronze.regiao_saude` | `cod_regiao_saude`, `nome`, `cod_uf` | `trim` em `cod_regiao_saude` e `cod_uf`. |

### 5.3. Camada `intermediate` (`transformacao/models/intermediate/`)

Contém a lógica de negócio dimensional, o cálculo de vigência SCD Tipo 2 e a explosão em paciente-dias:

| Modelo (`intermediate.*`) | Materialização | Grão | Colunas e Regra de Negócio |
| --- | --- | --- | --- |
| `int_capitulo` | View | 1 linha por capítulo da CID-10 (22 capítulos) | `capitulo_cid` (`'01'` a `'22'`), `inicio` (ex.: `'A00'`), `fim` (ex.: `'B99'`), `capitulo_nome`. Intervalos de 3 caracteres mutuamente exclusivos. |
| `int_estabelecimento_scd` | Table | 1 linha por versão de estabelecimento `(cnes, valido_de)` | Gera chave substituta `sk_estabelecimento`, `valido_de` (`competencia_inicio`), `valido_ate_exclusivo` (`LEAD(competencia_inicio)` ou `'9999-12-31'`), `valido_ate` (`valido_ate_exclusivo - 1 dia`), e resolve `cod_regiao_saude` (via `stg_regiao_df` quando `cod_municipio = '530010'`, senão via `stg_municipio`). |
| `int_internacao` | Table | 1 linha por AIH vigente `(competencia, n_aih, dt_saida)` | Faz o *as-of join* da AIH com `int_estabelecimento_scd` no mês de `dt_saida` (`valido_de <= date_trunc('month', dt_saida) < valido_ate_exclusivo`). Se a alta for anterior à primeira versão cadastral conhecida do hospital, usa a primeira versão e marca `cadastro_posterior = TRUE`. Associa também capítulo da CID e UF. |
| `int_leito_regiao_mes` | Table | 1 linha por `(cod_regiao_saude, competencia)` | Junta `stg_leito` à versão vigente do estabelecimento naquela competência e soma `sum(qt_sus)::bigint AS leitos_sus` por região de saúde e mês. |
| `int_paciente_dia` | **View** (grão fino não publicado) | 1 linha por paciente-dia ocupado | Para cada internação com `dias_permanencia > 0` e região conhecida, gera uma série diária de `dt_saida - dias_permanencia` até `dt_saida - 1` (`generate_series`), projetando `cod_regiao_saude`, `cod_uf`, `capitulo_cid`, `capitulo_nome`, `dia` e `semana` (`date_trunc('week', dia)` — segunda-feira ISO). |
| `int_semana` | Table | 1 linha por `(cod_regiao_saude, semana)` | Gera todas as segundas-feiras ISO de cada mês com `leitos_sus > 0`, agrega os `paciente_dias` de `int_paciente_dia`, calcula `ocupacao = paciente_dias / (leitos_sus * 7.0)`, define `acima_de_85 = (ocupacao > 0.85)` e marca `provisoria` via `stg_maturidade` (ou distância `< 3` meses até a última competência do SIH). |

---

## 6. Camada de Consumo Analítico (`PostgreSQL 16`, schema `consumo`)

Os modelos de `transformacao/models/marts/` são materializados no DuckDB e copiados por `transformacao/publicar.py` para o schema `consumo` do PostgreSQL. O painel Streamlit (`painel/app.py`) lê exclusivamente deste schema.

### 6.1. `consumo.dim_regiao_saude`

Dimensão geográfica das regiões de saúde do DF e de Goiás.

| Coluna | Tipo Postgres | Nulo? | Testes dbt (`_marts.yml`) | Descrição |
| --- | --- | --- | --- | --- |
| `cod_regiao_saude` | `TEXT` | Não | `not_null`, `unique` | Código identificador de 5 dígitos da região de saúde. |
| `nome` | `TEXT` | Não | `not_null` | Nome da região de saúde (ex.: `'Central'`, `'Oeste'`, `'Sul'`, `'Entorno Sul'`). |
| `cod_uf` | `TEXT` | Não | `not_null` | Código IBGE da UF (`'53'` para DF, `'52'` para GO). |

### 6.2. `consumo.dim_estabelecimento`

Dimensão de estabelecimentos em **Variação Lenta Tipo 2 (SCD Tipo 2)**. Preserva o histórico de mudanças de gestão, natureza jurídica, mantenedora e município sem reescrever o passado.

| Coluna | Tipo Postgres | Nulo? | Testes dbt | Descrição |
| --- | --- | --- | --- | --- |
| `sk_estabelecimento` | `BIGINT` | Não | `not_null`, `unique` | Chave substituta (*surrogate key*) da versão do estabelecimento (`row_number() OVER (ORDER BY cnes, valido_de)`). |
| `cnes` | `TEXT` | Não | `not_null`, `teste_scd_sem_sobreposicao` | Código CNES natural do estabelecimento (7 dígitos). |
| `valido_de` | `DATE` | Não | `not_null` | Data de início de vigência da versão (`AAAA-MM-01`). |
| `valido_ate` | `DATE` | Não | — | Data final inclusiva de vigência (`valido_ate_exclusivo - 1 dia`, ou `'9999-12-31'` na versão corrente). |
| `valido_ate_exclusivo` | `DATE` | Não | `teste_scd_sem_sobreposicao` | Data final exclusiva de vigência (`valido_de` da versão seguinte ou `'9999-12-31'`). |
| `cod_municipio` | `TEXT` | Não | — | Código IBGE (6 dígitos) do município na versão. |
| `cod_regiao_saude` | `TEXT` | Sim | `relationships -> dim_regiao_saude` | Região de saúde associada ao estabelecimento naquela vigência. |
| `tipo_unidade` | `TEXT` | Não | — | Código do tipo de unidade no CNES. |
| `tipo_gestao` | `TEXT` | Não | `not_null`, `accepted_values: ['E','M','D','S','F','Z']` | Esfera de gestão na vigência (`E`=Estadual, `M`=Municipal, `D`=Dupla, `S`=Sem gestão). |
| `natureza_juridica` | `TEXT` | Sim | — | Código CONCLA da natureza jurídica na vigência. |
| `cnpj_mantenedora` | `TEXT` | Sim | — | CNPJ da entidade mantenedora na vigência. |
| `vinculo_sus` | `BOOLEAN` | Sim | — | Indicador de vínculo com o SUS na vigência. |
| `atende_internacao` | `BOOLEAN` | Sim | — | Indicador de atendimento de internação na vigência. |
| `atende_urgencia` | `BOOLEAN` | Sim | — | Indicador de atendimento de urgência na vigência. |

### 6.3. `consumo.dim_cid`

Dimensão de diagnósticos CID-10 enriquecida com os 22 capítulos da OMS.

| Coluna | Tipo Postgres | Nulo? | Testes dbt | Descrição |
| --- | --- | --- | --- | --- |
| `cod_cid` | `TEXT` | Não | `not_null`, `unique` | Código da subcategoria/categoria CID-10 (ex.: `'J189'`). |
| `descricao` | `TEXT` | Não | — | Nome/descrição clínica do código CID-10. |
| `capitulo_cid` | `TEXT` | Não | `not_null` | Código de 2 dígitos do capítulo da CID-10 (`'01'` a `'22'`, ou `'99'` quando fora das faixas). |
| `capitulo_nome` | `TEXT` | Não | — | Título do capítulo da CID-10 (ex.: `'Doenças do aparelho respiratório'`). |

### 6.4. `consumo.dim_semana`

Dimensão de calendário semanal ISO por UF, incluindo o estado de maturidade do dado.

| Coluna | Tipo Postgres | Nulo? | Testes dbt | Descrição |
| --- | --- | --- | --- | --- |
| `semana` | `DATE` | Não | `not_null`, `teste_unicidade_semana (semana, cod_uf)` | Data da segunda-feira que inicia a semana ISO. |
| `cod_uf` | `TEXT` | Não | `not_null`, `teste_unicidade_semana (semana, cod_uf)` | Código IBGE da UF (`'53'` ou `'52'`). |
| `ano` | `BIGINT` | Não | — | Ano civil da segunda-feira (`year(semana)`). |
| `mes` | `DATE` | Não | — | Primeiro dia do mês civil da segunda-feira (`date_trunc('month', semana)`). |
| `semana_iso` | `BIGINT` | Não | — | Número da semana ISO no ano (`1` a `53`). |
| `ano_iso` | `BIGINT` | Não | — | Ano ISO correspondente à semana. |
| `provisoria` | `BOOLEAN` | Não | — | `TRUE` se o mês da semana ainda possui menos de 3 competências posteriores do SIH observadas naquela UF (sujeito à chegada de AIHs atrasadas). |

### 6.5. `consumo.fato_internacao`

Tabela fato ao nível de AIH paga na carga vigente, vinculada à versão do estabelecimento que vigorava no mês da saída do paciente.

| Coluna | Tipo Postgres | Nulo? | Testes dbt | Descrição |
| --- | --- | --- | --- | --- |
| `competencia` | `DATE` | Não | `teste_uma_versao_por_internacao` | Competência de processamento da AIH (`AAAA-MM-01`). |
| `n_aih` | `TEXT` | Não | `not_null`, `teste_uma_versao_por_internacao` | Número da AIH (13 dígitos). |
| `dt_saida` | `DATE` | Não | `not_null`, `teste_uma_versao_por_internacao` | Data de saída do paciente. |
| `cnes` | `TEXT` | Não | — | Código CNES natural do hospital. |
| `sk_estabelecimento` | `BIGINT` | Não | `not_null`, `relationships -> dim_estabelecimento` | Chave substituta da versão do hospital vigente no mês de `dt_saida`. |
| `cod_regiao_saude` | `TEXT` | Sim | `relationships -> dim_regiao_saude` | Região de saúde do estabelecimento na vigência da saída. |
| `cod_uf` | `TEXT` | Sim | — | Código IBGE da UF da região de saúde (`'53'` ou `'52'`). |
| `cid_principal` | `TEXT` | Não | `not_null`, `relationships -> dim_cid` | Código CID-10 do diagnóstico principal. |
| `capitulo_cid` | `TEXT` | Não | — | Código do capítulo da CID-10 (`'01'` a `'22'` / `'99'`). |
| `capitulo_nome` | `TEXT` | Não | — | Nome do capítulo da CID-10. |
| `dias_permanencia` | `INTEGER` | Não | — | Quantidade de dias de permanência da AIH. |
| `valor_total` | `NUMERIC(12,2)` | Não | — | Valor financeiro total aprovado na AIH (R$). |
| `municipio_residencia` | `TEXT` | Não | — | Código IBGE (6 dígitos) do município de residência do paciente. |
| `cadastro_posterior` | `BOOLEAN` | Não | — | `TRUE` quando `dt_saida` é anterior à primeira versão cadastral conhecida do CNES (fallback para a versão mais antiga disponível). |
| `construida_em` | `TIMESTAMPTZ` | Não | — | Carimbo de tempo de construção da linha pelo dbt. |

- **Índice de Otimização (`sql/e3/indice.sql`):**
  - `idx_fato_internacao_cnes_saida ON consumo.fato_internacao (cnes, dt_saida) INCLUDE (capitulo_cid, dias_permanencia)`

### 6.6. `consumo.ocupacao_semana_regiao`

Tabela fato agregada principal que responde à pergunta de gestão da plataforma. Grão: **1 linha por região de saúde por semana ISO**.

| Coluna | Tipo Postgres | Nulo? | Testes dbt | Descrição |
| --- | --- | --- | --- | --- |
| `cod_regiao_saude` | `TEXT` | Não | `not_null`, `relationships -> dim_regiao_saude`, `teste_unicidade_ocupacao` | Código da região de saúde (5 dígitos). |
| `cod_uf` | `TEXT` | Não | `teste_fk_semana` | Código IBGE da UF (`'53'` ou `'52'`). |
| `semana` | `DATE` | Não | `not_null`, `teste_unicidade_ocupacao`, `teste_fk_semana` | Segunda-feira da semana ISO (`AAAA-MM-DD`). |
| `ano` | `BIGINT` | Não | — | Ano civil da segunda-feira (`year(semana)`). Coluna de partição lógica no backfill anual. |
| `mes` | `DATE` | Não | — | Mês civil da segunda-feira (`AAAA-MM-01`), cujo cadastro CNES-LT fornece `leitos_sus`. |
| `semana_iso` | `BIGINT` | Não | — | Número da semana ISO (`1` a `53`). |
| `ano_iso` | `BIGINT` | Não | — | Ano ISO da semana. |
| `leitos_sus` | `BIGINT` | Não | `not_null`, `teste_ocupacao_distribuicao (> 0)` | Soma de `qt_sus` dos estabelecimentos da região na competência de `mes`. |
| `paciente_dias` | `BIGINT` | Não | `not_null`, `teste_volume_paciente_dia`, `teste_ocupacao_distribuicao (>= 0)` | Total de paciente-dias ocupados na região durante os 7 dias daquela semana. |
| `ocupacao` | `DOUBLE PRECISION` | Não | `teste_ocupacao_distribuicao (0 <= ocupacao < 5.0)` | Taxa de ocupação semanal estimada: $\text{ocupacao} = \frac{\text{paciente\_dias}}{\text{leitos\_sus} \times 7,0}$. |
| `acima_de_85` | `BOOLEAN` | Não | `not_null` | Indicador de sobrecarga hospitalar: `TRUE` quando `ocupacao > 0.85` (85%). |
| `provisoria` | `BOOLEAN` | Não | — | `TRUE` quando o mês da semana ainda está na janela de dado atrasado (< 3 competências subsequentes). |
| `construida_em` | `TIMESTAMPTZ` | Não | `not_null`, `teste_freshness_sla` | Carimbo de tempo de materialização do mart no dbt. |

- **Índice de Otimização (`sql/e3/indice.sql`):**
  - `idx_ocupacao_regiao_ano ON consumo.ocupacao_semana_regiao (cod_regiao_saude, ano, semana) INCLUDE (ocupacao, acima_de_85)`

### 6.7. `consumo.causa_semana_regiao`

Tabela fato que decompõe a ocupação semanal de cada região de saúde por capítulo da CID-10. Grão: **1 linha por `(cod_regiao_saude, semana, capitulo_cid)`** com pelo menos 1 paciente-dia.

| Coluna | Tipo Postgres | Nulo? | Testes dbt | Descrição |
| --- | --- | --- | --- | --- |
| `cod_regiao_saude` | `TEXT` | Não | `not_null`, `relationships -> dim_regiao_saude`, `teste_unicidade_causa` | Código da região de saúde (5 dígitos). |
| `semana` | `DATE` | Não | `not_null`, `teste_unicidade_causa` | Segunda-feira da semana ISO. |
| `ano` | `BIGINT` | Não | — | Ano civil da semana (`year(semana)`). Usado pelo backfill anual. |
| `capitulo_cid` | `TEXT` | Não | `not_null`, `teste_unicidade_causa` | Código de 2 dígitos do capítulo da CID-10 (`'01'` a `'22'` / `'99'`). |
| `capitulo_nome` | `TEXT` | Não | — | Nome do capítulo da CID-10. |
| `paciente_dias` | `BIGINT` | Não | `not_null`, `teste_volume_paciente_dia` | Total de paciente-dias daquele capítulo da CID na região e semana. |
| `parcela` | `DOUBLE PRECISION` | Não | `not_null`, `teste_parcelas_cid (soma = 1.0 ± 0.0001)` | Fração dos paciente-dias da semana explicada pelo capítulo: $\frac{\text{paciente\_dias}}{\sum \text{paciente\_dias da semana na região}}$. |
| `construida_em` | `TIMESTAMPTZ` | Não | — | Carimbo de tempo de materialização do mart no dbt. |

### 6.8. `consumo.sla` e `consumo.controle_freshness`

Tabelas de governança de atualização e monitoramento do Acordo de Nível de Serviço (SLA de 24 horas).

#### `consumo.sla` (`transformacao/models/marts/sla.sql`)

| Coluna | Tipo Postgres | Nulo? | Testes dbt | Descrição |
| --- | --- | --- | --- | --- |
| `tabela` | `TEXT` | Não | `not_null`, `unique` | Nome da tabela monitorada (`'ocupacao_semana_regiao'`). |
| `sla_horas` | `INTEGER` | Não | `not_null` | Limite máximo de defasagem declarado em horas (`24`). |
| `descricao` | `TEXT` | Não | — | Regra operacional do SLA e horário da agenda diária (`06:00`). |

#### `consumo.controle_freshness` (`transformacao/publicar.py`)

| Coluna | Tipo Postgres | Nulo? | Chave | Descrição |
| --- | --- | --- | --- | --- |
| `tabela` | `TEXT` | Não | `PRIMARY KEY` | Nome da tabela monitorada (`'ocupacao_semana_regiao'`). |
| `construida_em` | `TIMESTAMPTZ` | Sim | — | Maior `construida_em` registrado em `marts.ocupacao_semana_regiao`. |
| `ingerido_em` | `TIMESTAMPTZ` | Sim | — | Maior `_ingerido_em` lido de `staging.stg_internacao` (`lote.internacao`). |
| `atraso_horas` | `DOUBLE PRECISION` | Sim | — | Horas decorridas entre `construida_em` e o instante da publicação. |
| `sla_horas` | `INTEGER` | Não | — | Limite do SLA em horas (`24`). |
| `dentro_do_sla` | `BOOLEAN` | Não | — | `TRUE` se `atraso_horas <= 24` e `construida_em >= ingerido_em`. Verificado pelo asset `freshness` no Dagster. |
| `medido_em` | `TIMESTAMPTZ` | Não | — | Instante UTC em que a verificação foi gravada. |

---

## 7. Camada Semântica / Banco Vetorial (`PostgreSQL 16 + pgvector`)

Criada pela migração `0008_pgvector.py` e populada por `semantico/experimento.py` para avaliar busca por similaridade de cosseno contra o filtro determinístico `acima_de_85` (ver [ADR 0004](adr/0004-cosseno-nao-e-o-limiar.md)).

### 7.1. `semantico.trecho`

| Coluna | Tipo SQL | Nulo? | Chave / Restrição | Descrição |
| --- | --- | --- | --- | --- |
| `id` | `BIGINT` | Não | `PRIMARY KEY` (`GENERATED ALWAYS AS IDENTITY`) | Identificador sequencial do trecho textual. |
| `cod_regiao_saude` | `TEXT` | Não | `UNIQUE (cod_regiao_saude, semana)` | Código da região de saúde (5 dígitos). |
| `nome_regiao` | `TEXT` | Não | — | Nome da região de saúde. |
| `semana` | `DATE` | Não | `UNIQUE (cod_regiao_saude, semana)` | Segunda-feira da semana ISO. |
| `ano` | `INTEGER` | Não | — | Ano civil da semana. |
| `ocupacao` | `DOUBLE PRECISION` | Não | — | Taxa de ocupação semanal copiada de `consumo.ocupacao_semana_regiao`. |
| `acima_de_85` | `BOOLEAN` | Não | — | Indicador booleano (`ocupacao > 0.85`) copiado do mart. |
| `capitulo_cid` | `TEXT` | Sim | — | Capítulo da CID-10 com maior número de paciente-dias naquela região e semana. |
| `capitulo_nome` | `TEXT` | Sim | — | Nome do capítulo da CID-10 predominante na semana. |
| `texto` | `TEXT` | Não | — | Frase em linguagem natural sintetizada a partir da linha do mart (`semantico/frases.py`). |
| `embedding` | `vector(384)` | Não | Índice HNSW `trecho_embedding_hnsw` | Vetor denso de 384 dimensões gerado localmente pelo modelo `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`. |

- **Índice Vetorial:**
  - `CREATE INDEX trecho_embedding_hnsw ON semantico.trecho USING hnsw (embedding vector_cosine_ops)`

---

## 8. Domínios, Códigos de Referência e Fórmulas de Negócio

### 8.1. Regiões de Saúde do Distrito Federal (`cod_uf = '53'`)

| Código (`cod_regiao_saude`) | Região de Saúde | Exemplos de Regiões Administrativas / Hospitais (`estabelecimento_regiao_df`) |
| --- | --- | --- |
| `53002` | Oeste | Ceilândia, Brazlândia (HRC, HRBZ, Hospital Anchieta Ceilândia) |
| `53003` | Sudoeste | Taguatinga, Samambaia, Águas Claras (HRT, HRSAM, HSVP, Hospital Santa Marta) |
| `53004` | Sul | Gama, Santa Maria (HRG, HRSM) |
| `53005` | Centro-Sul | Guará (HRGU) |
| `53006` | Central | Plano Piloto, Cruzeiro, Lago Sul, Lago Norte (HBDF, HRAN, HUB, HMIB, HCB, HAB, ICDF, Sarah) |
| `53007` | Norte | Sobradinho, Planaltina (HRS, HRPL) |
| `53008` | Leste | Paranoá, São Sebastião, Jardim Botânico (HRL, Casa de Parto de São Sebastião) |

*(Nota: O código `53001` aparece em arquivos históricos do TabWin como "Brasília — Distrito Federal" agregado, mas todos os hospitais do DF com internação são alocados nas 7 regiões operacionais `53002` a `53008` via `estabelecimento_regiao_df`.)*

### 8.2. Domínios de Códigos do SUS

| Atributo | Código | Significado |
| --- | --- | --- |
| **`fonte` (`carga`)** | `'SIH_RD'` | Sistema de Informações Hospitalares do SUS — AIH Reduzida (`RD*.dbc`) |
| | `'CNES_ST'` | Cadastro Nacional de Estabelecimentos de Saúde — Estabelecimentos (`ST*.dbc`) |
| | `'CNES_LT'` | Cadastro Nacional de Estabelecimentos de Saúde — Leitos (`LT*.dbc`) |
| | `'REFERENCIA'` | Pacote auxiliar `TAB_SIH.zip` e CSV curado `estabelecimento_regiao_saude_df.csv` |
| **`ident` (`internacao`)** | `'1'` | AIH Principal (internação normal) |
| | `'3'` | AIH de Continuação |
| | `'5'` | AIH de Longa Permanência (cobrada em faturas mensais sucessivas; exige `dt_saida` na PK) |
| **`tipo_gestao`** | `'E'` | Estadual / Distrital (padrão da SES-DF) |
| | `'M'` | Municipal |
| | `'D'` | Dupla (Estadual e Municipal) |
| | `'S'` | Sem gestão / Federal |
| | `'F'`, `'Z'` | Códigos legados aceitos pelo contrato de esquema do dbt |
| **`cod_idade`** | `'2'` | Idade expressa em dias |
| | `'3'` | Idade expressa em meses |
| | `'4'` | Idade expressa em anos |
| | `'5'` | Idade expressa em centena de anos (100 + `idade`) |

### 8.3. Capítulos da CID-10 (`intermediate.int_capitulo` e `consumo.dim_cid`)

| Código (`capitulo_cid`) | Faixa de Categorias (`inicio`–`fim`) | Nome do Capítulo (`capitulo_nome`) |
| --- | --- | --- |
| `'01'` | `A00` – `B99` | Doenças infecciosas e parasitárias |
| `'02'` | `C00` – `D48` | Neoplasias |
| `'03'` | `D50` – `D89` | Doenças do sangue |
| `'04'` | `E00` – `E90` | Doenças endócrinas |
| `'05'` | `F00` – `F99` | Transtornos mentais |
| `'06'` | `G00` – `G99` | Doenças do sistema nervoso |
| `'07'` | `H00` – `H59` | Doenças do olho |
| `'08'` | `H60` – `H95` | Doenças do ouvido |
| `'09'` | `I00` – `I99` | Doenças do aparelho circulatório |
| `'10'` | `J00` – `J99` | Doenças do aparelho respiratório |
| `'11'` | `K00` – `K93` | Doenças do aparelho digestivo |
| `'12'` | `L00` – `L99` | Doenças da pele |
| `'13'` | `M00` – `M99` | Doenças do sistema osteomuscular |
| `'14'` | `N00` – `N99` | Doenças do aparelho geniturinário |
| `'15'` | `O00` – `O99` | Gravidez, parto e puerpério |
| `'16'` | `P00` – `P96` | Afecções do período perinatal |
| `'17'` | `Q00` – `Q99` | Malformações congênitas |
| `'18'` | `R00` – `R99` | Sintomas e sinais |
| `'19'` | `S00` – `T98` | Lesões e envenenamentos |
| `'20'` | `V01` – `Y98` | Causas externas |
| `'21'` | `Z00` – `Z99` | Fatores que influenciam o estado de saúde |
| `'22'` | `U00` – `U99` | Códigos para propósitos especiais |
| `'99'` | *(Fallback)* | Não classificado |

### 8.4. Resumo das Fórmulas e Regras Analíticas

1. **Expansão de Paciente-Dia (`int_paciente_dia`):**
   - Cada AIH com $\text{dias\_permanencia} > 0$ gera $\text{dias\_permanencia}$ registros diários no intervalo fechado:
     $$[\text{dt\_saida} - \text{dias\_permanencia},\; \text{dt\_saida} - 1]$$
   - Justificativa: em AIHs de longa permanência (`ident = '5'`), `dt_internacao` registra a admissão original (às vezes anos antes), enquanto `dias_permanencia` reflete apenas os dias faturados naquele período até `dt_saida`.
2. **Alocação Semanal (`int_semana`):**
   - Cada dia ocupado $d$ é alocado à segunda-feira da sua semana ISO (`date_trunc('week', d)`).
   - O denominador de capacidade (`leitos_sus`) de uma semana é o total de leitos SUS vigentes na região de saúde no mês da segunda-feira que inicia aquela semana (`date_trunc('month', semana)`).
3. **Taxa de Ocupação Semanal Estimada (`ocupacao_semana_regiao.ocupacao`):**
   $$\text{ocupacao} = \frac{\text{paciente\_dias}}{\text{leitos\_sus} \times 7,0}$$
4. **Indicador de Excesso de Ocupação (`ocupacao_semana_regiao.acima_de_85`):**
   $$\text{acima\_de\_85} = (\text{leitos\_sus} > 0) \land (\text{ocupacao} > 0,85)$$
5. **Parcela de Causa por Capítulo da CID-10 (`causa_semana_regiao.parcela`):**
   $$\text{parcela}_{r, s, c} = \frac{\text{paciente\_dias}_{r, s, c}}{\sum_{k} \text{paciente\_dias}_{r, s, k}}$$
   onde $r$ é a região de saúde, $s$ é a semana ISO e $c$ é o capítulo da CID-10.
