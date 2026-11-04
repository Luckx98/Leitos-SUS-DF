-- Grão fino, não persistido: um paciente-dia, da véspera da alta para trás,
-- tantos dias quanto dias_permanencia. A longa permanência cobra por período;
-- dt_internacao seria a data original, não o início deste período (mesma regra da L4).
with estadia as (
    select
        cod_regiao_saude,
        cod_uf,
        capitulo_cid,
        capitulo_nome,
        cast(dt_saida - dias_permanencia as date) as dia_inicio,
        cast(dt_saida - 1 as date) as dia_fim
    from {{ ref('int_internacao') }}
    where dias_permanencia > 0
      and cod_regiao_saude is not null
)
select
    e.cod_regiao_saude,
    e.cod_uf,
    e.capitulo_cid,
    e.capitulo_nome,
    cast(s.dia as date) as dia,
    cast(date_trunc('week', cast(s.dia as date)) as date) as semana
from estadia as e,
lateral generate_series(e.dia_inicio, e.dia_fim, interval 1 day) as s(dia)
where e.dia_inicio <= e.dia_fim
