-- Uma linha por semana e UF na dimensão.
select semana, cod_uf, count(*) as linhas
from {{ ref('dim_semana') }}
group by 1, 2
having count(*) > 1
