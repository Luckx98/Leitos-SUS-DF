-- Buraco de série: segunda-feira de um mês com leito SUS que não aparece na ocupação.
-- Na amostra só existe o recorte carregado; não se exige o calendário de 2021 a 2025.
{% set anos = var('anos', []) %}
with meses as (
    select distinct cod_regiao_saude, competencia, leitos_sus
    from {{ ref('int_leito_regiao_mes') }}
    where leitos_sus > 0
),
esperado as (
    select m.cod_regiao_saude, cast(s.semana as date) as semana
    from meses as m,
    lateral generate_series(
        cast(date_trunc('week', m.competencia) as date),
        cast(date_trunc('week', m.competencia + interval 1 month - interval 1 day) as date),
        interval 7 day
    ) as s(semana)
    where cast(date_trunc('month', cast(s.semana as date)) as date) = m.competencia
)
select e.cod_regiao_saude, e.semana
from esperado as e
left join {{ ref('ocupacao_semana_regiao') }} as o
    on o.cod_regiao_saude = e.cod_regiao_saude
   and o.semana = e.semana
where o.semana is null
{% if anos | length > 0 %}
  and year(e.semana) in ({{ anos | join(', ') }})
{% endif %}
