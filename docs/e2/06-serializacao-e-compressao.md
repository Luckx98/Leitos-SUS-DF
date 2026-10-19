# Serialização e compressão

Três decisões, todas medidas sobre as internações carregadas (`lakehouse/medir_formatos.py`):

```bash
docker compose run --rm loader python -m lakehouse.medir_formatos > medicoes/e2/formatos_AAAA-MM-DD.txt
```

## 1. Codec do Parquet: zstd

| Codec | Tamanho | B/linha | Escrita | Pontual | Agregação de um ano | Varredura completa |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| nenhum | 124,7 MB | 34,0 | 3,4 s | 7,0 ms | 30,1 ms | 66,7 ms |
| snappy | 80,2 MB | 21,9 | 3,7 s | 7,3 ms | 27,3 ms | 69,4 ms |
| **zstd** | **62,2 MB** | **17,0** | 3,8 s | 7,8 ms | 30,1 ms | 70,7 ms |
| gzip | 58,2 MB | 15,9 | 32,3 s | 10,8 ms | 35,4 ms | 74,6 ms |

O gzip grava 8,5× mais devagar para economizar só 4 MB sobre o zstd, com leitura equivalente. O zstd é o melhor custo-benefício.

## 2. Partição de `internacao`: por ano, não por mês

| Variante | Arquivos | MB médio/arquivo | Consulta pontual (1 hospital, 1 mês) |
| --- | ---: | ---: | ---: |
| sem partição | 1 | 62,25 | 8,1 ms |
| por ano | 7 | 8,96 | 8,9 ms |
| **por mês** | **72** | **0,96** | **6,6 ms** |

Por mês, as 3,67 milhões de internações viram 72 arquivos de menos de 1 MB — bem abaixo do tamanho recomendado para Parquet/Iceberg — com a mesma latência da consulta pontual que a partição por ano. A AIH atrasada cai no ano em que o paciente saiu, e o reprocessamento da janela ([Dado atrasado](05-dado-atrasado.md)) apaga e regrava só as linhas dos últimos meses — o Iceberg reescreve apenas os arquivos afetados, não a tabela inteira. As demais tabelas são pequenas (leito: ~2 MB em Parquet) e ficam sem partição.

## 3. Mensagens do CDC: JSON + zstd, sem Avro

| Formato | B/evento | 3,67 milhões de eventos |
| --- | ---: | ---: |
| JSON | 1.004,5 | 3,69 GB |
| JSON + zstd (lote 16 KB) | 77,1 | 0,28 GB |
| **JSON + zstd (lote 1 MB)** | **41,3** | **0,15 GB** |
| Avro | 307,6 | 1,13 GB |
| Avro + zstd (lote 16 KB) | 41,4 | 0,15 GB |
| Avro + zstd (lote 1 MB) | 35,7 | 0,13 GB |

JSON sem compressão custa 1 KB por evento; comprimido em lotes de 1 MB no produtor, cai para 41,3 B — praticamente o mesmo que Avro comprimido (35,7 B), sem precisar de um schema registry. O Debezium Server publica em JSON por padrão; manter o formato e comprimir no produtor (`infra/debezium/application.properties`: `compression.type=zstd`, `batch.size=1048576`) evita uma dependência extra para a mesma economia.

Resultado completo em `medicoes/e2/formatos_2026-10-19.txt`.
