# Testes

Os testes genéricos ficam em `transformacao/models/marts/_marts.yml`. Os que olham o dado sujo do domínio são SQL em `transformacao/tests/` e falham quando devolvem linha.

| Teste | O que pega |
| --- | --- |
| esquema (`not_null`, `accepted_values` de gestão, contratos de coluna) | coluna que sumiu ou gestão fora de E, M, D, S, F, Z |
| `teste_volume_internacao` | fato com mais ou menos AIHs do que a carga vigente |
| `teste_volume_paciente_dia` | paciente-dia da semana diferente do fato semanal |
| `teste_unicidade_ocupacao`, `teste_unicidade_causa`, `teste_unicidade_semana` | grão duplicado |
| `relationships` e `teste_fk_semana` | fato apontando para dimensão que não existe |
| `teste_uma_versao_por_internacao` | AIH sem versão de estabelecimento, ou com mais de uma |
| `teste_scd_sem_sobreposicao` | vigências do mesmo CNES se cruzando — a dimensão tratada como sobrescrita |
| `teste_ocupacao_distribuicao` | ocupação negativa, leito negativo ou ocupação de 500% ou mais |
| `teste_parcelas_cid` | parcelas de capítulo que não somam 1 |
| `teste_buraco_de_serie` | segunda-feira de um mês com leito que não aparece na ocupação |
| `teste_regiao_que_some` | região do DF com leito no primeiro ano da série e nenhuma linha no último |
| `teste_freshness_sla` | consumo construído mais de uma hora antes do lote, ou há mais de 24 horas |
| `teste_serie_completa` | na carga completa, o DF não cobre 2021–2025 |

`teste_buraco_de_serie` olha os meses que a carga tem. Na amostra (DF, 01/2025) ele não exige o calendário de cinco anos. `teste_serie_completa` só roda com `serie_completa: true`, que o pipeline liga quando `MODO=completo`. `SERIE_COMPLETA=0` desliga essa exigência num recorte curto de propósito.

O `dbt build` roda modelo e teste juntos. Uma falha impede a publicação.
