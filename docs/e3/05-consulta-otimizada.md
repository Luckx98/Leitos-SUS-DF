# Consulta otimizada

A pergunta no mart semanal é um filtro por região, ano e ocupação. Mesmo na carga completa isso é uma linha por região por semana: centenas de linhas, não milhões. O plano que muda é o de `fato_internacao`, no acesso por estabelecimento e data de saída — o mesmo acesso que a origem já indexava na E1 (`idx_internacao_cnes_saida`) e que o mart precisa devolver sem varrer a AIH.

`transformacao/explicar.py` roda no fim da publicação completa:

1. remove os índices, faz `ANALYZE` e grava `EXPLAIN (ANALYZE, BUFFERS)` de cada consulta;
2. cria os índices de `sql/e3/indice.sql`, faz `ANALYZE` de novo e grava o plano de depois;
3. grava também o plano da L4 na origem, como contexto: é a expansão de paciente-dia que esta camada materializa uma vez.

Arquivos, todos em `medicoes/e3/`:

| Arquivo | Consulta |
| --- | --- |
| `explain_fato_internacao_antes.txt` | capítulos de um estabelecimento, sem índice |
| `explain_fato_internacao_depois.txt` | a mesma consulta, com `(cnes, dt_saida)` |
| `explain_ocupacao_antes.txt` | semanas de uma região acima de 85%, sem índice |
| `explain_ocupacao_depois.txt` | a mesma consulta, com `(cod_regiao_saude, ano, semana)` |
| `explain_l4_origem.txt` | a L4 direto na origem |

Na amostra a tabela semanal é pequena e o planejador pode continuar na varredura mesmo com o índice. O arquivo guarda o plano que o Postgres escolheu, não um plano forçado. O índice de `fato_internacao` é o que passa a ser usado quando o filtro por estabelecimento é seletivo.

Esses cinco arquivos nascem quando o perfil `e3` publica o consumo. O que esta sessão mediu, sem o Docker no ar, está em `medicoes/e3/granularidade_2026-11-04.txt` e no [ADR 0003](../adr/0003-estrela-semanal-sobre-dbt.md).
