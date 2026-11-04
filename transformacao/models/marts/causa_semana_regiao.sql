-- Uma linha por região de saúde, por semana ISO e por capítulo da CID-10.
-- A parcela é a fração dos paciente-dias daquela semana. O painel filtra as
-- semanas em que a ocupação passou de 85%.
with base as (
    select
        cod_regiao_saude,
        semana,
        capitulo_cid,
        any_value(capitulo_nome) as capitulo_nome,
        count(*)::bigint as paciente_dias
    from {{ ref('int_paciente_dia') }}
    group by 1, 2, 3
)
select
    cod_regiao_saude,
    semana,
    year(semana) as ano,
    capitulo_cid,
    capitulo_nome,
    paciente_dias,
    paciente_dias / sum(paciente_dias) over (partition by cod_regiao_saude, semana) as parcela,
    current_timestamp as construida_em
from base
where true
{{ filtrar_anos('semana') }}
