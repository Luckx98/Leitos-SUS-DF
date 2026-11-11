-- Uma linha por AIH paga na carga vigente, com a versão do estabelecimento na data da saída.
select
    competencia,
    n_aih,
    dt_saida,
    cnes,
    sk_estabelecimento,
    cod_regiao_saude,
    cod_uf,
    cid_principal,
    capitulo_cid,
    capitulo_nome,
    dias_permanencia,
    valor_total,
    municipio_residencia,
    cadastro_posterior,
    current_timestamp as construida_em
from {{ ref('int_internacao') }}
where true
{{ filtrar_anos('dt_saida') }}
