-- A tabela de consumo foi construída depois do lote e tem menos de 24 horas.
-- No backfill de um ano o mart não contém a série inteira; o SLA é da publicação completa.
{% if var('anos', []) | length == 0 %}
with limites as (
    select
        max(construida_em) as construida,
        (select max(_ingerido_em) from {{ ref('stg_internacao') }}) as ingerido
    from {{ ref('ocupacao_semana_regiao') }}
)
select construida, ingerido
from limites
where construida is null
   or ingerido is null
   or date_diff('hour', cast(ingerido as timestamptz), cast(construida as timestamptz)) < -1
   or date_diff('hour', cast(construida as timestamptz), current_timestamp) > 24
{% else %}
select 1 where false
{% endif %}
