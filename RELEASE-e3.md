# Release Notes 3 — Banco de Dados 2

Nome do grupo: Grupo 01 — Leitos SUS-DF
Integrantes:

| Nome                              | Matrícula |
| --------------------------------- | --------- |
| Lucas Macedo Barboza              | 190091720 |
| Caetano Santos Lucio              | 180144979 |
| Cairo Florenço                    | 222014975 |
| Leonardo Sobrinho                 | 200022199 |
| Carlos Eduardo Mendes de Mesquita | 190085584 |
| Bruna de Lima                     | 211041105 |
| Lais Cecília                      | 211029512 |

Data: 04/11/2026
Domínio: capacidade de leitos e internações do SUS no Distrito Federal e em Goiás
Entrega: E3 — camada analítica (14% da nota)

A Release 2 deixou o lakehouse no ar: `lote.*` reprocessa a janela de dado atrasado e `cdc.*` cobre a latência de segundos. Esta release lê o lote e entrega a pergunta da E1 já agregada, testada e reconstruída sozinha.

---

## 1. Estrela no grão da semana

Uma linha de `ocupacao_semana_regiao` é uma região de saúde numa semana ISO: paciente-dia, leitos SUS da competência, ocupação e o indicador acima de 85%. `causa_semana_regiao` abre essa semana por capítulo da CID-10. O paciente-dia existe na transformação e não é publicado.

`dim_estabelecimento` é variação lenta tipo 2. A internação junta a versão vigente no mês da saída. A L4 da E1 usava a versão mais recente e reescrevia o passado; aqui uma mudança de gestão em março não altera janeiro.

Evidência: `transformacao/models/`, [ADR 0003](docs/adr/0003-estrela-semanal-sobre-dbt.md).

## 2. dbt, com a opção nula no repositório

Três camadas (staging sobre `lote.*`, intermediate, marts) no DuckDB, publicadas no schema Postgres `consumo`. A opção nula é `sql/e3/opcao_nula.sql`: a mesma conta na origem, no cron, com o cadastro de hoje e sem teste.

A L4 na origem custa 6,4 s para um ano (`docs/e1/05-caracterizacao-da-carga.md`). No recorte que valida o SQL (20 AIHs, janeiro de 2025), agregar o paciente-dia na hora levou 1,29 ms e ler o mart semanal levou 0,14 ms (`medicoes/e3/granularidade_2026-11-04.txt`). O `dbt build` desse recorte fechou com 77 passos sem erro. O tempo da opção nula no Postgres e os planos `EXPLAIN (ANALYZE, BUFFERS)` saem de `python -m transformacao` com o perfil no ar.

## 3. Testes que pegam dado sujo

Além de nulo e de chave, o `dbt build` recusa vigência sobreposta no mesmo CNES, ocupação negativa ou de 500% ou mais, parcela de capítulo que não soma 1, semana com leito que some da série, AIH sem exatamente uma versão de estabelecimento, e consumo com mais de 24 horas. O buraco de série olha os meses que a carga tem. A exigência de 2021–2025 só liga com `MODO=completo`.

## 4. Agenda, retry e backfill

O Dagster sobe na porta 3000. O grafo diário, às 06:00, é `lote_conferido → marts → publicar_consumo → freshness`. A publicação tem uma nova tentativa. `scripts/demo_retry.sh` derruba a primeira de propósito. `scripts/demo_backfill.sh` publica um ano que a carga não tem e depois preenche cada ano presente, sem apagar os outros. As saídas ficam em `medicoes/e3/`.

O perfil `e3` não sobe Redpanda, Debezium nem o consumidor de CDC. A máquina de referência não comporta os dois ao mesmo tempo.

## 5. Freshness

`consumo.ocupacao_semana_regiao` carrega `construida_em`. O SLA declarado é de 24 horas depois do avanço do lote. `consumo.controle_freshness` e `consumo.sla` publicam a conta, e o painel mostra se está dentro.

## 6. Painel

Streamlit na porta 8501, lendo só `consumo`: a série com a linha de 85%, as semanas acima disso (provisória ou madura) e os capítulos da CID nesse excesso. Distrito Federal e, no mesmo recorte, Goiás. Na amostra o painel avisa que a série de cinco anos exige `MODO=completo`.

## 7. Decisão registrada

➡️ [ADR 0003 — Estrela semanal, construída com dbt, publicada no Postgres](docs/adr/0003-estrela-semanal-sobre-dbt.md)

## 8. Pipeline de dados (versão da E3)

```text
FONTES → ORIGEM → LOTE → dbt (staging, intermediate, marts) → consumo → painel
                              ↑
                         Dagster (agenda, retry, backfill)
```

O CDC continua no perfil `e2` e não alimenta esta camada.

| Etapa | O que faz | Onde |
| --- | --- | --- |
| Lote | snapshot atual de `lote.*` | perfil `e2` ou `e3` |
| Transformação | camadas dbt e testes | `transformacao/` |
| Publicação | marts no schema `consumo`, índices, planos | `transformacao/publicar.py`, `transformacao/explicar.py` |
| Orquestração | agenda diária, retry, backfill por ano | `orquestracao/` |
| Painel | semanas acima de 85% e capítulos da CID | `painel/app.py` |

Status atual:

- **Sobe do clone, sem rede, na amostra:** `docker compose --profile e3 up --build`.
- **Números da série 2021–2025:** `MODO=completo`. O arquivo de granularidade desta data é o recorte de verificação do SQL, não essa série.
- **Diário de bordo:** `docs/diario/2026-11-04.md`.

Documentação da entrega: [docs/e3/](docs/e3/index.md).
