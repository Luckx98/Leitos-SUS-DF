# ADR 0004 — Cosseno da frase do mart, sem substituir o limiar

- **Status:** Aceito
- **Data:** 2026-11-11
- **Decisores:** Squad Grupo 01 (Leitos SUS-DF)

## Contexto

A estrela da E3 já publica a ocupação semanal e o indicador acima de 85% em `consumo`. A etapa seguinte da disciplina é o banco vetorial: a pesquisa e a pontuação são outras, e a integração semântica só fica confiável quando essa diferença tiver sido medida. Esta decisão cobre o experimento, não a entrega final.

**Carga de trabalho:** uma frase por região e semana, montada com colunas que o mart já tem (ocupação, leitos, paciente-dia, capítulo da CID, se passou de 85%). A amostra é DF, 01/2025, e sobe sem rede. A máquina de referência tem 8 CPUs e cerca de 6 GB; o perfil `e3` não sobe o CDC.

**Restrições:** software livre, sem chave de API, o mesmo Postgres da origem, e o número da ocupação continua saindo do warehouse.

## Alternativas consideradas

|     | Alternativa                                            | Prós                                                                                                                                                         | Custos                                                                                           |
| --- | ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| 0   | **Não guardar vetor.** A pergunta segue no SQL do mart | a resposta de 85% já está correta                                                                                                                            | não mede a pontuação que a etapa vetorial usa                                                    |
| 1   | **Qdrant (ou outro cluster) com um modelo por API**    | é um banco vetorial “de verdade”, separado                                                                                                                   | segundo serviço na máquina que já cortou o CDC; a amostra passaria a depender de rede e de chave |
| 2   | **pgvector no Postgres 16, embedding local na imagem** | a extensão mora no banco que já existe; o modelo `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensões, ~0,22 GB) cabe na imagem e a amostra não baixa nada | o ANN e o cosseno não são o `EXPLAIN` de um B-tree; 384 dimensões fixas na tabela                |

## Decisão

Guardar em `semantico.trecho` a frase do mart e o vetor dessa frase, com pgvector no mesmo Postgres. A ordenação é `embedding <=> pergunta` (distância de cosseno). O limiar `consumo.ocupacao_semana_regiao.acima_de_85` não é derivado do vetor e não é substituído por ele.

Três perguntas comparam o top-5 com o conjunto SQL das semanas acima de 85%: “pico de causa respiratória”, “falta de leito no inverno” e “semana em que a ocupação passou de 85%”. A terceira existe para mostrar que as palavras “passou de 85%” também estão na frase que diz “não passou”.

## Medição

Série DF e GO publicada em `consumo`, 7.500 frases, 207 semanas com `acima_de_85`. Modelo local, índice HNSW `vector_cosine_ops`, top-5. Arquivo: `medicoes/e3/vetor_2026-11-11.txt`.

| Pergunta                               | No top-5 e acima de 85% | O que o vizinho mais próximo é                                           |
| -------------------------------------- | ----------------------: | ------------------------------------------------------------------------ |
| pico de causa respiratória             |                  0 de 5 | Nordeste I, 2022-06-27, ocupação 6,9%, causa respiratória                |
| falta de leito no inverno              |                  0 de 5 | Nordeste I, 2022-07-11, ocupação 0,5%, causa respiratória                |
| semana em que a ocupação passou de 85% |                  0 de 5 | Nordeste I, 2023-07-17, ocupação 7,3%, causa gravidez, parto e puerpério |

As 207 semanas acima de 85% ficaram fora dos três topos. A ordenação usou `Index Scan` em `trecho_embedding_hnsw` (`embedding <=> pergunta`), em 0,51 ms, 0,22 ms e 0,15 ms. Não é o índice `(região, ano, semana)` do mart.

## Consequências

- Uma semana respiratória abaixo de 85% pode ficar à frente de uma semana que estourou o limiar por outra causa. O cosseno não aplica o indicador.
- A pergunta que repete o texto do limiar pode aproximar a frase que nega o limiar, porque os tokens se sobrepõem. A coluna booleana continua sendo a resposta da E1.
- Filtro de UF, ano e o indicador de 85% permanecem no warehouse. O vetor não recalcula paciente-dia.
- Não há chatbot nem RAG. O painel continua lendo só `consumo`.
- A integração semântica — a pergunta em linguagem natural devolvendo o número do mart, e não o vizinho mais parecido — fica para a entrega final. A evidência deste experimento está em `medicoes/e3/vetor_*.txt`.
