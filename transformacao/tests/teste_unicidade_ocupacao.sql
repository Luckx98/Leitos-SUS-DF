-- Grão da ocupação: uma linha por região por semana.
select cod_regiao_saude, semana, count(*) as linhas
from {{ ref('ocupacao_semana_regiao') }}
group by 1, 2
having count(*) > 1
