-- Distribuição: ocupação negativa, leito negativo ou ocupação acima de 5
-- (500%) indicam dia contado duas vezes ou leito zerado tratado como demanda.
select cod_regiao_saude, semana, paciente_dias, leitos_sus, ocupacao
from {{ ref('ocupacao_semana_regiao') }}
where paciente_dias < 0
   or leitos_sus < 0
   or (leitos_sus = 0 and ocupacao is not null)
   or (ocupacao is not null and (ocupacao < 0 or ocupacao >= 5))
