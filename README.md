# Leitos SUS-DF

**A capacidade de leitos do SUS acompanha a demanda por internação?**

Plataforma de dados do Grupo 01 de Banco de Dados 2 (UnB/FCTE, 2026/2). Ela cruza a capacidade de leitos do SUS (CNES) com as internações pagas pelo SUS (SIH/SUS) no Distrito Federal e em Goiás, para mostrar onde e quando a ocupação passa do limite.

## Pergunta de gestão

> Entre 2021 e 2025, em quais semanas do ano a ocupação estimada de leitos SUS (paciente-dia ÷ leitos cadastrados) ultrapassou 85% em cada região de saúde do DF, e quais causas de internação (CID) concentravam esse excesso?

**Persona:** gestor da Secretaria de Saúde do DF e da Central de Regulação de Leitos.

## Pipeline de dados

```text
FONTES ──► MIGRAÇÕES ──► CARGA ──► BANCO DE ORIGEM ──► LOTE e CDC ──► LAKEHOUSE (ICEBERG)
```

(`LOTE` e `CDC` são dois caminhos paralelos, não um passo único — ver o diagrama em [docs/index.md](docs/index.md) ou no [site publicado](https://luckx98.github.io/Leitos-SUS-DF/).)

- **FONTES:** arquivos públicos do DATASUS com as internações (SIH/SUS) e os estabelecimentos e leitos (CNES) do DF e de Goiás, de 2021 até a última competência publicada, mais as tabelas de CID-10, municípios e regiões de saúde. Um recorte versionado em `dados/amostra/` permite subir a plataforma sem rede.
- **MIGRAÇÕES:** o PostgreSQL sobe e o esquema é criado a partir de um banco vazio, em ordem, antes de qualquer carga.
- **CARGA:** o loader baixa os arquivos, valida cada linha e grava um arquivo por transação. Arquivos já carregados são ignorados; linhas inválidas ficam registradas com o motivo.
- **BANCO DE ORIGEM:** PostgreSQL insert-only, que nunca sobrescreve: guarda as versões do cadastro, os leitos mês a mês e, em cada internação, a data do evento, a competência e a data de carga. Sobe pronto para a captura de mudanças (`wal_level=logical`), usada a partir daqui.
- **LOTE:** exportação incremental, por marca d'água de carga, com reprocessamento da janela de dado atrasado. O caminho mais barato; cobre a carga inicial e o reprocessamento em massa.
- **CDC:** Debezium lê o WAL lógico e publica no Redpanda; um consumidor Python grava no Iceberg com latência de segundos.
- **LAKEHOUSE (ICEBERG):** os dois caminhos escrevem o mesmo esquema, em namespaces separados (`lote.*` e `cdc.*`), para poderem ser reconciliados e comparados. Decisão e medições no [ADR 0002](docs/adr/0002-lote-incremental-e-cdc-sobre-iceberg.md).

## Componentes

| Componente | Responsabilidade |
| --- | --- |
| PostgreSQL 16 | banco de origem insert-only, com `wal_level=logical` |
| Alembic | migrações versionadas em `alembic/versions/` |
| Loader (Python 3.11) | download do FTP do DATASUS, validação e carga em `loader/` |
| Docker Compose | sobe banco, migrações e carga com um comando |
| MkDocs Material | documentação publicada no GitHub Pages |

## Equipe

| Nome | Matrícula |
| --- | --- |
| Lucas Macedo Barboza | 190091720 |
| Caetano Santos Lucio | 180144979 |
| Cairo Florenço | 222014975 |
| Leonardo Sobrinho | 200022199 |
| Carlos Eduardo Mendes de Mesquita | 190085584 |
| Bruna de Lima | 211041105 |
| Lais Cecília | 211029512 |


## Executar o projeto

Requisito: Docker com Docker Compose. O arquivo `.env` é opcional, porque o `docker-compose.yml` já tem valores padrão. Para mudar algum valor, copie o `.env.example`.

```bash
git clone https://github.com/Luckx98/Leitos-SUS-DF.git
cd Leitos-SUS-DF
docker compose up --build
```

O Compose sobe três serviços, nesta ordem:

1. `postgres`: PostgreSQL 16 com `wal_level=logical`;
2. `migrate`: aplica as migrações de `alembic/versions/` num banco vazio;
3. `loader`: carrega as tabelas de referência e os dados do SIH/SUS e do CNES e termina com um resumo das contagens.

### Modos de carga

| Modo | O que carrega | Rede | Tempo aproximado |
| --- | --- | --- | --- |
| `amostra` (padrão) | Recorte versionado em `dados/amostra/` (DF, 01/2025) | Não precisa | < 1 min |
| `completo` | DF e GO de 01/2021 até a última competência publicada, baixados do FTP do DATASUS | Precisa | ~15 min, ~330 MB baixados |

```bash
MODO=completo docker compose up --build -d
docker compose logs -f loader      # acompanhar o progresso
docker compose ps -a               # leitos_loader "Exited (0)" = carga concluída sem falhas
```

Para limitar o recorte, use as variáveis `UFS`, `COMPETENCIA_INICIO` e `COMPETENCIA_FIM`, no formato `AAAA-MM`:

```bash
MODO=completo UFS=DF COMPETENCIA_INICIO=2024-01 COMPETENCIA_FIM=2024-12 docker compose up --build
```

A carga é idempotente: um arquivo já carregado com o mesmo conteúdo é ignorado. Se o FTP cair no meio, basta rodar o mesmo comando de novo. Os arquivos já baixados ficam no volume `leitos_dados_brutos` e não são baixados outra vez.

### Consultar o banco

Conexão: `localhost:5432`, banco `leitos`, usuário `leitos`, senha `leitos`. Se a porta 5432 já estiver em uso, suba com `POSTGRES_PORT=55432 docker compose up --build`.

```bash
docker compose exec postgres psql -U leitos -d leitos -c \
  "SELECT fonte, count(*) arquivos, sum(linhas_inseridas) inseridas, sum(linhas_rejeitadas) rejeitadas FROM carga GROUP BY 1"
```

### Testes e qualidade dos dados

```bash
docker compose run --rm loader python -m unittest          # testes do loader
docker compose run --rm loader python -m loader.qualidade  # verificações sobre os dados carregados
```

As verificações de qualidade também rodam automaticamente no fim de toda carga. Uma verificação com erro faz o loader terminar com código 1.

### Perfil e2 — lakehouse (lote e CDC)

Além dos três serviços da E1, o perfil `e2` sobe um lakehouse Iceberg alimentado por dois caminhos a partir da mesma origem: um lote incremental e um fluxo de CDC (Debezium → Redpanda → consumidor Python). Os dois escrevem o mesmo esquema, em `lote.*` e `cdc.*`, para poderem ser comparados. Decisão e medições completas: [ADR 0002](docs/adr/0002-lote-incremental-e-cdc-sobre-iceberg.md).

```bash
docker compose --profile e2 up --build -d
docker compose logs -f cdc
```

Sobe mais cinco serviços: SeaweedFS (S3, porta `${S3_PORT:-8333}`), Redpanda (Kafka, porta externa `${KAFKA_PORT:-19092}`), Debezium, `lakehouse-init` (catálogo e buckets) e `lote`. Conferir que os dois caminhos batem com a origem:

```bash
docker compose run --rm --no-deps lote python -m lakehouse.reconciliar
```

Demonstrações prontas (com o perfil `e2` no ar):

| Script | O que mostra |
| --- | --- |
| `scripts/demo_cdc.sh [UF] [COMPETENCIA]` | uma competência nova na origem chega a `cdc.internacao` sem passo manual |
| `scripts/demo_semantica.sh` | releitura do CDC com e sem deduplicação, e viagem no tempo no Iceberg |
| `scripts/compactar_cdc.sh` | junta os arquivos pequenos de `cdc.*` (precisa parar o consumidor) |
| `scripts/medir_ingestao.sh [COMPETENCIA]` | custo do lote, do snapshot do CDC e de uma competência nova, com memória e CPU por fase |

### Recomeçar do zero

```bash
docker compose down -v   # apaga o banco, os arquivos baixados e o lakehouse
```

## Documentação

A documentação completa está no [GitHub Pages do Leitos SUS-DF](https://luckx98.github.io/Leitos-SUS-DF/).

| Tema | Página |
| --- | --- |
| Domínio e pergunta de gestão | [docs/e1/01-dominio-e-pergunta.md](docs/e1/01-dominio-e-pergunta.md) |
| Esquema e migrações | [docs/e1/02-esquema-e-migracoes.md](docs/e1/02-esquema-e-migracoes.md) |
| Carga reprodutível | [docs/e1/03-carga-reprodutivel.md](docs/e1/03-carga-reprodutivel.md) |
| Volume | [docs/e1/04-volume.md](docs/e1/04-volume.md) |
| Caracterização da carga | [docs/e1/05-caracterizacao-da-carga.md](docs/e1/05-caracterizacao-da-carga.md) |
| Histórico da origem | [docs/e1/06-historico-da-origem.md](docs/e1/06-historico-da-origem.md) |
| ADR 0001 — origem insert-only | [docs/adr/0001-origem-insert-only-versionada-por-competencia.md](docs/adr/0001-origem-insert-only-versionada-por-competencia.md) |
| Visão da E2 — lakehouse por lote e CDC | [docs/e2/index.md](docs/e2/index.md) |
| Lote incremental | [docs/e2/01-lote-incremental.md](docs/e2/01-lote-incremental.md) |
| CDC | [docs/e2/02-cdc.md](docs/e2/02-cdc.md) |
| Formato aberto | [docs/e2/03-formato-aberto.md](docs/e2/03-formato-aberto.md) |
| Semântica de entrega | [docs/e2/04-semantica-de-entrega.md](docs/e2/04-semantica-de-entrega.md) |
| Dado atrasado | [docs/e2/05-dado-atrasado.md](docs/e2/05-dado-atrasado.md) |
| Serialização e compressão | [docs/e2/06-serializacao-e-compressao.md](docs/e2/06-serializacao-e-compressao.md) |
| ADR 0002 — lote e CDC sobre Iceberg | [docs/adr/0002-lote-incremental-e-cdc-sobre-iceberg.md](docs/adr/0002-lote-incremental-e-cdc-sobre-iceberg.md) |
| Uso de IA | [AI-USAGE.md](AI-USAGE.md) |

Para visualizar o site localmente:

```bash
python -m venv .venv-docs
source .venv-docs/bin/activate
python -m pip install -r requirements-docs.txt
mkdocs serve
```

Abra <http://127.0.0.1:8000>. O MkDocs atualiza a página automaticamente quando um arquivo em `docs/` é salvo.

## Estrutura principal

```text
alembic/versions/   migrações do banco (0001–0006)
loader/             download, validação e carga das fontes do DATASUS
tests/              testes do loader
dados/amostra/      recorte versionado (DF, 01/2025) para subir sem rede
dados/referencia/   região de saúde dos hospitais do DF (tabela curada)
sql/caracterizacao/ medição de volume, escrita, leitura e defasagem
sql/historico/      consultas que dependem do histórico da origem
sql/adr/            medição das alternativas do ADR 0001
lakehouse/          lakehouse Iceberg: lote incremental, consumidor de CDC, janela, compactação
infra/              configuração do Debezium e do SeaweedFS
scripts/            demonstrações e medições do perfil e2 (CDC, semântica, ingestão)
medicoes/e2/        resultados medidos do perfil e2 (formatos, ingestão, Iceberg x Delta, semântica)
docs/               documentação publicada pelo MkDocs
```

## Fontes e licença dos dados

- **SIH/SUS — AIH reduzida (RD)** e **CNES — estabelecimentos (ST) e leitos (LT)**: Ministério da Saúde, DATASUS. FTP público: `ftp://ftp.datasus.gov.br/dissemin/publicos/`.
- **Tabelas auxiliares** (CID-10, municípios, regiões de saúde): DATASUS, pacote `TAB_SIH.zip`.
- **Portal de Dados Abertos do SUS**: <https://dadosabertos.saude.gov.br/>.

Os dados do Portal de Dados Abertos do SUS são publicados sob a licença [Creative Commons Atribuição-SemDerivações 3.0](https://creativecommons.org/licenses/by-nd/3.0/deed.pt_BR). Este repositório publica código e agregados, cita a fonte e não republica a base modificada. Os arquivos brutos não são versionados, exceto o recorte de teste em `dados/amostra/`: três arquivos `.dbc` originais e um pacote com três tabelas do `TAB_SIH.zip`, todos sem alteração de conteúdo.

Os dados de internação são dados de saúde (LGPD, art. 5º, II). A origem não grava data de nascimento, CEP nem CPF, e a plataforma publica apenas agregados.
