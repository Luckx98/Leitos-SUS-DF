select
    trim(cod_municipio) as cod_municipio,
    nome,
    trim(cod_uf) as cod_uf,
    nullif(trim(cod_regiao_saude), '') as cod_regiao_saude
from {{ source('espelho', 'municipio') }}
