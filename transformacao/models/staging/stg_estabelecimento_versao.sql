-- Todas as versões do cadastro. Uma competência republicada não cria uma segunda linha
-- para o mesmo (cnes, competencia_inicio): fica a de maior id_carga.
select
    trim(cnes) as cnes,
    competencia_inicio,
    trim(cod_municipio) as cod_municipio,
    trim(tipo_unidade) as tipo_unidade,
    trim(tipo_gestao) as tipo_gestao,
    nullif(trim(natureza_juridica), '') as natureza_juridica,
    nullif(trim(cnpj_mantenedora), '') as cnpj_mantenedora,
    vinculo_sus,
    atende_internacao,
    atende_urgencia
from {{ source('bronze', 'estabelecimento_versao') }}
qualify row_number() over (
    partition by trim(cnes), competencia_inicio
    order by id_carga desc
) = 1
