-- Uma linha por versão de cadastro de um estabelecimento, vigente de competencia_inicio
-- até a véspera da versão seguinte. Atributos que mudam: gestão, natureza jurídica,
-- mantenedora, município. A região do DF vem da tabela curada; em GO, do município.
with versoes as (
    select
        v.cnes,
        v.competencia_inicio as valido_de,
        coalesce(
            lead(v.competencia_inicio) over (partition by v.cnes order by v.competencia_inicio),
            date '9999-12-31'
        ) as valido_ate_exclusivo,
        v.cod_municipio,
        case
            when v.cod_municipio = '530010' then df.cod_regiao_saude
            else m.cod_regiao_saude
        end as cod_regiao_saude,
        v.tipo_unidade,
        v.tipo_gestao,
        v.natureza_juridica,
        v.cnpj_mantenedora,
        v.vinculo_sus,
        v.atende_internacao,
        v.atende_urgencia
    from {{ ref('stg_estabelecimento_versao') }} as v
    left join {{ ref('stg_regiao_df') }} as df on df.cnes = v.cnes
    left join {{ ref('stg_municipio') }} as m on m.cod_municipio = v.cod_municipio
)
select
    row_number() over (order by cnes, valido_de) as sk_estabelecimento,
    cnes,
    valido_de,
    valido_ate_exclusivo,
    case
        when valido_ate_exclusivo = date '9999-12-31' then date '9999-12-31'
        else cast(valido_ate_exclusivo - interval 1 day as date)
    end as valido_ate,
    cod_municipio,
    cod_regiao_saude,
    tipo_unidade,
    tipo_gestao,
    natureza_juridica,
    cnpj_mantenedora,
    vinculo_sus,
    atende_internacao,
    atende_urgencia
from versoes
