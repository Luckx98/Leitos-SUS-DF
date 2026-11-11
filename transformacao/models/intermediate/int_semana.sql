-- Uma linha por região de saúde por semana ISO (a segunda-feira).
-- O leito é o do mês dessa segunda-feira. Semana sem leito não entra:
-- a ocupação não se define. Paciente-dia ausente vale zero.
with limites as (
    select
        cod_regiao_saude,
        cod_uf,
        competencia,
        leitos_sus,
        cast(date_trunc('week', competencia) as date) as primeira,
        cast(date_trunc('week', competencia + interval 1 month - interval 1 day) as date) as ultima
    from {{ ref('int_leito_regiao_mes') }}
    where leitos_sus > 0
),
semanas as (
    select
        l.cod_regiao_saude,
        l.cod_uf,
        l.leitos_sus,
        cast(s.semana as date) as semana
    from limites as l,
    lateral generate_series(l.primeira, l.ultima, interval 7 day) as s(semana)
    where cast(date_trunc('month', cast(s.semana as date)) as date) = l.competencia
),
dias as (
    select cod_regiao_saude, semana, count(*)::bigint as paciente_dias
    from {{ ref('int_paciente_dia') }}
    group by 1, 2
),
referencia as (
    select uf, max(competencia) as competencia
    from {{ ref('stg_carga_vigente') }}
    where fonte = 'SIH_RD'
    group by 1
)
select
    s.cod_regiao_saude,
    s.cod_uf,
    s.semana,
    year(s.semana) as ano,
    cast(date_trunc('month', s.semana) as date) as mes,
    week(s.semana) as semana_iso,
    isoyear(s.semana) as ano_iso,
    s.leitos_sus,
    coalesce(d.paciente_dias, 0) as paciente_dias,
    case
        when s.leitos_sus > 0 then coalesce(d.paciente_dias, 0) / (s.leitos_sus * 7.0)
    end as ocupacao,
    coalesce(
        s.leitos_sus > 0 and coalesce(d.paciente_dias, 0) / (s.leitos_sus * 7.0) > 0.85,
        false
    ) as acima_de_85,
    coalesce(
        mat.status = 'provisório',
        date_diff(
            'month',
            cast(date_trunc('month', s.semana) as date),
            ref.competencia
        ) < 3,
        true
    ) as provisoria
from semanas as s
left join dias as d
    on d.cod_regiao_saude = s.cod_regiao_saude
   and d.semana = s.semana
left join {{ ref('stg_maturidade') }} as mat
    on mat.uf = case s.cod_uf when '53' then 'DF' when '52' then 'GO' else s.cod_uf end
   and mat.mes_saida = cast(date_trunc('month', s.semana) as date)
left join referencia as ref
    on ref.uf = case s.cod_uf when '53' then 'DF' when '52' then 'GO' else s.cod_uf end
