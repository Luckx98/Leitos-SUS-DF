# Consulta otimizada

A pergunta no mart semanal é um filtro por região, ano e ocupação. Mesmo na carga completa isso é uma linha por região por semana: centenas de linhas, não milhões. O plano que muda é o de `fato_internacao`, no acesso por estabelecimento e data de saída — o mesmo acesso que a origem já indexava na E1 (`idx_internacao_cnes_saida`) e que o mart precisa devolver sem varrer a AIH.

`transformacao/explicar.py` roda no fim da publicação completa:

1. remove os índices, faz `ANALYZE` e grava `EXPLAIN (ANALYZE, BUFFERS)` de cada consulta;
2. cria os índices de `sql/e3/indice.sql`, faz `ANALYZE` de novo e grava o plano de depois;
3. grava também o plano da L4 na origem, como contexto: é a expansão de paciente-dia que esta camada materializa uma vez.

Arquivos, todos em `medicoes/e3/`:

| Arquivo                              | Consulta                                                |
| ------------------------------------ | ------------------------------------------------------- |
| `explain_fato_internacao_antes.txt`  | capítulos de um estabelecimento, sem índice             |
| `explain_fato_internacao_depois.txt` | a mesma consulta, com `(cnes, dt_saida)`                |
| `explain_ocupacao_antes.txt`         | semanas de uma região acima de 85%, sem índice          |
| `explain_ocupacao_depois.txt`        | a mesma consulta, com `(cod_regiao_saude, ano, semana)` |
| `explain_l4_origem.txt`              | a L4 direto na origem                                   |

Na amostra (20.995 internações, 28 semanas) o plano de `fato_internacao` passou de varredura sequencial, 2,51 ms, para `Bitmap Index Scan` em `(cnes, dt_saida)`, 1,16 ms. A tabela semanal continuou em varredura: 28 linhas cabem numa página, e o planejador não usa o índice. O arquivo guarda o plano que o Postgres escolheu, não um plano forçado.

A L4 na mesma origem levou 774 ms. O número de 6,4 s da E1 é um ano da carga completa, não esta amostra. Os cinco arquivos da amostra estão em `medicoes/e3/amostra/`.

Na série DF e GO os arquivos de `medicoes/e3/explain_*.txt` são os de 2026-11-11. A L4 na origem, com `EXPLAIN (ANALYZE, BUFFERS)`, levou 165,9 s. A mesma SQL cronometrada fora do `EXPLAIN` levou 55,5 s. O CNES 0010456, o de mais AIHs entre 2021 e 2025, saiu em 204,5 ms na varredura paralela e em 376,0 ms no índice: o filtro devolve cerca de 132 mil linhas, e o bitmap perde para a varredura. A semana da região 52011 em 2026, com `ocupacao >= 0,85`, não tem linha; a varredura levou 0,64 ms e o índice 0,17 ms.
