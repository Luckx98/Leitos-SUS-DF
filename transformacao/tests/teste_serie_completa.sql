-- Na carga completa, o DF precisa cobrir 2021 a 2025. Na amostra o teste não exige isso.
{% if var('serie_completa', false) %}
with df as (
    select min(ano) as primeiro, max(ano) as ultimo, count(distinct ano) as anos
    from {{ ref('ocupacao_semana_regiao') }}
    where cod_uf = '53'
)
select primeiro, ultimo, anos
from df
where primeiro > 2021
   or ultimo < 2025
   or anos < 5
{% else %}
select 1 where false
{% endif %}
