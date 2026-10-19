# Formato aberto

As tabelas do lakehouse são Iceberg (formato v2) sobre Parquet, lidas pelo DuckDB sem precisar reimplementar nenhum motor de consulta.

## Catálogo e armazenamento

- **Catálogo:** SQL catalog (`pyiceberg.catalog.sql.SqlCatalog`) no banco `iceberg`, no mesmo PostgreSQL da origem (`lakehouse/catalogo.py`). Guarda só os ponteiros para os metadados; os dados ficam no S3.
- **Armazenamento de objetos:** SeaweedFS, compatível com S3. O MinIO foi descartado porque não publica mais imagem pública no Docker Hub nem no Quay (conferido antes de decidir).
- **Dois namespaces, um esquema:** `lote.*` e `cdc.*` têm as mesmas cinco tabelas e colunas, para poderem ser reconciliadas e comparadas ([ADR 0002](../adr/0002-lote-incremental-e-cdc-sobre-iceberg.md)).

## Esquema (`lakehouse/esquemas.py`)

Cada tabela repete as colunas da origem e acrescenta colunas de controle:

| Coluna | Significado |
| --- | --- |
| `_op` | operação na origem (`c` = insert, `r` = leitura do snapshot) |
| `_lsn` | posição no WAL (só no CDC) |
| `_commit_em` | quando a linha foi gravada na origem |
| `_ingerido_em` | quando a linha foi gravada no Iceberg |

A diferença entre as duas últimas é a latência do caminho, usada em `lakehouse/reconciliar.py`. Todos os campos são opcionais no Iceberg: a integridade já é garantida na origem (PK, FK, CHECK) e conferida por reconciliação, não reimposta aqui.

## Particionamento oculto

`internacao` é particionada pelo **ano** de `dt_saida` (`YearTransform`). As demais tabelas são pequenas e ficam sem partição. A coluna física continua sendo `dt_saida`; quem consulta não precisa saber que existe partição.

## Por que Iceberg e não Delta Lake

| | escrita | tamanho | leitura (DuckDB) | evolução de partição (mês → ano) |
| --- | ---: | ---: | ---: | --- |
| Iceberg | 0,5 s | 13,1 MB | 7,8 ms | **0,01 s, só metadado** |
| Delta | 0,7 s | 16,6 MB | 11,6 ms | **0,42 s, reescreve a tabela inteira** |

Medido com `lakehouse/medir_iceberg_delta.py` sobre 696.700 internações com saída em 2024 (`medicoes/e2/iceberg_delta_2026-10-19.txt`). O critério decisivo foi a evolução de partição: esta própria entrega precisou mudar a partição de `internacao` de mês para ano ([Serialização e compressão](06-serializacao-e-compressao.md)), e com Iceberg isso custou só metadado — com Delta, que particiona por pasta física, teria exigido reescrever a tabela inteira e mudar a consulta de quem já filtrava pela coluna antiga.

Detalhe completo das alternativas e da medição: [ADR 0002](../adr/0002-lote-incremental-e-cdc-sobre-iceberg.md).
