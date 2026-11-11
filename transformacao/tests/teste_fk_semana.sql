-- Semana da ocupação aponta para a dimensão (semana, UF).
select o.semana, o.cod_uf
from {{ ref('ocupacao_semana_regiao') }} as o
left join {{ ref('dim_semana') }} as d
    on d.semana = o.semana
   and d.cod_uf = o.cod_uf
where d.semana is null
