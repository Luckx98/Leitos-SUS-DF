-- Leitos SUS da versão do estabelecimento vigente naquela competência, somados por região.
select
    e.cod_regiao_saude,
    r.cod_uf,
    l.competencia,
    sum(l.qt_sus)::bigint as leitos_sus
from {{ ref('stg_leito') }} as l
inner join {{ ref('int_estabelecimento_scd') }} as e
    on e.cnes = l.cnes
   and l.competencia >= e.valido_de
   and l.competencia < e.valido_ate_exclusivo
inner join {{ ref('stg_regiao_saude') }} as r on r.cod_regiao_saude = e.cod_regiao_saude
where e.cod_regiao_saude is not null
group by 1, 2, 3
