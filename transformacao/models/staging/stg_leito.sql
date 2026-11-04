-- Retrato mensal de leitos da carga vigente do CNES-LT.
select
    l.competencia,
    trim(l.cnes) as cnes,
    trim(l.cod_leito) as cod_leito,
    l.qt_sus
from {{ source('espelho', 'leito') }} as l
inner join {{ ref('stg_carga_vigente') }} as c
    on c.id_carga = l.id_carga
   and c.fonte = 'CNES_LT'
