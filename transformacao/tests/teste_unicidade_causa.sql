-- Grão da causa: uma linha por região, semana e capítulo.
select cod_regiao_saude, semana, capitulo_cid, count(*) as linhas
from {{ ref('causa_semana_regiao') }}
group by 1, 2, 3
having count(*) > 1
