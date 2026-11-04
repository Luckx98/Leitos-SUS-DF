-- Volume: o fato tem uma linha para cada AIH da staging vigente.
-- No backfill de um ano o mart é um recorte; a igualdade vale para a construção completa.
{% if var('anos', []) | length == 0 %}
select fato, staging
from (
    select
        (select count(*) from {{ ref('fato_internacao') }}) as fato,
        (select count(*) from {{ ref('stg_internacao') }}) as staging
)
where fato <> staging
{% else %}
select 1 where false
{% endif %}
