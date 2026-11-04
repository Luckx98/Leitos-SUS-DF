select
    trim(cod_cid) as cod_cid,
    descricao
from {{ source('bronze', 'cid') }}
