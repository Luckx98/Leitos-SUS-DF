-- Uma linha por CID-10, com o capítulo.
select
    c.cod_cid,
    c.descricao,
    coalesce(cap.capitulo_cid, '99') as capitulo_cid,
    coalesce(cap.capitulo_nome, 'Não classificado') as capitulo_nome
from {{ ref('stg_cid') }} as c
left join {{ ref('int_capitulo') }} as cap
    on left(c.cod_cid, 3) between cap.inicio and cap.fim
