-- As parcelas de capítulo de uma semana somam 1. Fora disso, paciente-dia vazou ou foi contado duas vezes.
select cod_regiao_saude, semana, sum(parcela) as soma
from {{ ref('causa_semana_regiao') }}
group by 1, 2
having abs(sum(parcela) - 1) > 0.001
    or min(parcela) < 0
    or max(parcela) > 1
