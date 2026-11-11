select
    trim(cod_regiao_saude) as cod_regiao_saude,
    nome,
    trim(cod_uf) as cod_uf
from {{ source('bronze', 'regiao_saude') }}
