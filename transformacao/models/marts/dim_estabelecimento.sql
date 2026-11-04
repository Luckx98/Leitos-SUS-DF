-- Uma linha por versão vigente de um estabelecimento.
select
    sk_estabelecimento,
    cnes,
    valido_de,
    valido_ate,
    valido_ate_exclusivo,
    cod_municipio,
    cod_regiao_saude,
    tipo_unidade,
    tipo_gestao,
    natureza_juridica,
    cnpj_mantenedora,
    vinculo_sus,
    atende_internacao,
    atende_urgencia
from {{ ref('int_estabelecimento_scd') }}
