select
    trim(cnes) as cnes,
    nome_fantasia,
    trim(cod_regiao_saude) as cod_regiao_saude
from {{ source('espelho', 'estabelecimento_regiao_df') }}
