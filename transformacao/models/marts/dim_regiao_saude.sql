-- Uma linha por região de saúde.
select
    cod_regiao_saude,
    nome,
    cod_uf
from {{ ref('stg_regiao_saude') }}
