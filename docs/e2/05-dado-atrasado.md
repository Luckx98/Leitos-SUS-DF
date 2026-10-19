# Dado atrasado e reprocessamento de janela

O SIH processa a AIH depois da alta: na E1, 85,5% das saídas chegam em até 1 competência, e 99,5% em até 3. Como `lote.internacao` é organizada pela data de saída (`dt_saida`), uma competência nova sempre acrescenta linhas a meses que já foram exportados antes.

## Duas partes (`lakehouse/janela.py`)

1. **Reprocessamento da janela.** A cada lote com internações novas, as linhas dos últimos **3 meses de saída** são apagadas e regravadas, numa única transação do Iceberg, com o estado atual da origem até a marca d'água do lote. Idempotente: corrige também uma carga que tenha sido confirmada fora de ordem.
2. **Maturidade.** `lote.maturidade` marca cada mês de saída como `provisório` (menos de 3 competências observadas depois dele) ou `maduro`. Análises de sazonalidade — a própria pergunta de gestão da E1 — devem usar só meses maduros.

```bash
python -m lakehouse.janela              # janela padrão de 3 meses
python -m lakehouse.janela --meses 6
```

## Medido: competência nova (08/2026, DF+GO)

| Mês de saída | Linhas antes | Linhas depois |
| --- | ---: | ---: |
| 05/2026 | 63.233 | 63.233 |
| 06/2026 | 55.589 | 55.589 |
| 07/2026 | 50.210 | 50.210 |
| 08/2026 | 41.965 | 41.965 |

`lote.maturidade`: 146 meses classificados, 6 provisórios (GO e DF de 06, 07 e 08/2026 — exatamente os 3 meses mais recentes de cada UF). O reprocessamento completo da janela levou 18 s, dentro do custo do lote incremental ([Lote incremental](01-lote-incremental.md)). Reproduzir: `scripts/medir_ingestao.sh`, Fase 3; resultado em `medicoes/e2/ingestao_2026-10-19.txt`.

## Limitação conhecida

`pyiceberg` 0.12 não grava em fluxo numa tabela particionada — por isso o reprocessamento usa `delete` seguido de `append` em blocos (`lakehouse/janela.py:93`), em vez de uma única operação de sobrescrita. A coluna `_ingerido_em` também é regravada a cada reprocessamento, então a latência do lote só pode ser medida antes da janela passar por uma linha.
