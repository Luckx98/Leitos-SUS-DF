-- Uma linha por arquivo concluído, a carga de maior id_carga de cada fonte, UF e competência.
-- É a mesma regra de carga_vigente da origem: republicar um arquivo não duplica o fato.
select
    id_carga,
    trim(fonte) as fonte,
    trim(uf) as uf,
    competencia,
    status
from {{ source('bronze', 'carga') }}
where status = 'concluida'
  and competencia is not null
qualify row_number() over (
    partition by trim(fonte), trim(uf), competencia
    order by id_carga desc
) = 1
