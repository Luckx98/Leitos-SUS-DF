-- Paciente-dia de uma semana que está na ocupação tem de bater com a contagem do fato semanal.
select d.cod_regiao_saude, d.semana, d.paciente_dias as no_detalhe, o.paciente_dias as no_fato
from (
    select p.cod_regiao_saude, p.semana, count(*) as paciente_dias
    from {{ ref('int_paciente_dia') }} as p
    inner join {{ ref('int_semana') }} as s
        on s.cod_regiao_saude = p.cod_regiao_saude
       and s.semana = p.semana
    group by 1, 2
) as d
inner join {{ ref('ocupacao_semana_regiao') }} as o
    on o.cod_regiao_saude = d.cod_regiao_saude
   and o.semana = d.semana
where d.paciente_dias <> o.paciente_dias
