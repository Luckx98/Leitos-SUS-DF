# Banco vetorial — experimento

O warehouse responde com a coluna `acima_de_85`. O banco vetorial responde com vizinhos de texto. As duas contas não são a mesma, e esta página mostra a diferença. A integração semântica, em que a pergunta em linguagem natural devolve o número do mart, fica para a entrega final.

A imagem do Postgres passou a ser `pgvector/pgvector:pg16`: o mesmo PostgreSQL 16 da origem, com a extensão `vector`. Não entra um segundo cluster. A máquina de referência já não comporta o CDC junto com o perfil `e3`.

## O que vira vetor

Uma linha de `semantico.trecho` é uma região de saúde numa semana ISO. A frase sai de `consumo.ocupacao_semana_regiao` e do capítulo da CID com mais paciente-dias naquela semana. O paciente-dia não é recalculado. A ocupação, os leitos e o “passou” ou “não passou” de 85% entram como palavras, porque é isso que o mart já sabe dizer.

O modelo é o `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensões), gravado na imagem em `/app/modelos`. A amostra não baixa modelo nem usa chave de API. A migração `0008` cria a extensão e a tabela. O índice HNSW (`vector_cosine_ops`) é criado depois da carga, em `semantico/experimento.py`.

## As três perguntas

| Pergunta                               | O que o cosseno tende a aproximar                                             | O que o SQL devolve                           |
| -------------------------------------- | ----------------------------------------------------------------------------- | --------------------------------------------- |
| pico de causa respiratória             | semanas cuja frase cita o capítulo respiratório, tenham ou não passado de 85% | toda semana com `acima_de_85`, qualquer causa |
| falta de leito no inverno              | semanas cujo texto fala de ocupação alta; o inverno não é uma coluna          | a mesma lista, sem filtro de estação          |
| semana em que a ocupação passou de 85% | frases com essas palavras, inclusive as que dizem “não passou de 85%”         | só as linhas em que a coluna é verdadeira     |

O top-k é 5. Na série publicada em 2026-11-11 (7.500 frases, 207 semanas acima de 85%) os três topos tiveram **0 de 5** acima do limiar, e as 207 ficaram de fora. “Pico de causa respiratória” aproximou semanas respiratórias com ocupação entre 6,9% e 42,8%. “Falta de leito no inverno” aproximou semanas respiratórias com ocupação entre 0,5% e 18,6%, inclusive janeiro e dezembro. “Semana em que a ocupação passou de 85%” aproximou semanas de 4,6% a 13,3%, causa gravidez, parto e puerpério: a frase que diz “não passou” divide as palavras com a pergunta. O plano é `Index Scan` em `trecho_embedding_hnsw`, 0,15 ms a 0,51 ms, não o B-tree de `(região, ano, semana)`.

```bash
scripts/demo_vetor.sh
```

O resultado fica em `medicoes/e3/vetor_*.txt`. A decisão está no [ADR 0004](../adr/0004-cosseno-nao-e-o-limiar.md).
