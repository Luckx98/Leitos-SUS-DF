-- Uma linha por AIH paga na carga vigente. _ingerido_em é o instante em que o lote gravou a linha.
select
    i.competencia,
    trim(i.n_aih) as n_aih,
    i.dt_saida,
    i.id_carga,
    trim(i.cnes) as cnes,
    i.dt_internacao,
    i.dias_permanencia,
    trim(i.cid_principal) as cid_principal,
    cast(i.valor_total as decimal(12, 2)) as valor_total,
    trim(i.municipio_residencia) as municipio_residencia,
    cast(i._ingerido_em as timestamptz) as _ingerido_em
from {{ source('bronze', 'internacao') }} as i
inner join {{ ref('stg_carga_vigente') }} as c
    on c.id_carga = i.id_carga
   and c.fonte = 'SIH_RD'
