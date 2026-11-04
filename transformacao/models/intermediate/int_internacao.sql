-- Uma linha por AIH, com a versão do estabelecimento vigente no mês da saída.
-- Se a saída é anterior à primeira versão conhecida, usa essa primeira versão
-- e marca cadastro_posterior: a série não é reescrita com o cadastro de hoje.
with pares as (
    select
        i.competencia,
        i.n_aih,
        i.dt_saida,
        i.cnes,
        i.dias_permanencia,
        i.cid_principal,
        i.valor_total,
        i.municipio_residencia,
        i._ingerido_em,
        e.sk_estabelecimento,
        e.cod_regiao_saude,
        e.valido_de,
        r.cod_uf,
        coalesce(cap.capitulo_cid, '99') as capitulo_cid,
        coalesce(cap.capitulo_nome, 'Não classificado') as capitulo_nome,
        (
            e.valido_de <= cast(date_trunc('month', i.dt_saida) as date)
            and cast(date_trunc('month', i.dt_saida) as date) < e.valido_ate_exclusivo
        ) as cobre
    from {{ ref('stg_internacao') }} as i
    inner join {{ ref('int_estabelecimento_scd') }} as e on e.cnes = i.cnes
    left join {{ ref('stg_regiao_saude') }} as r on r.cod_regiao_saude = e.cod_regiao_saude
    left join {{ ref('int_capitulo') }} as cap
        on left(i.cid_principal, 3) between cap.inicio and cap.fim
)
select
    competencia,
    n_aih,
    dt_saida,
    cnes,
    dias_permanencia,
    cid_principal,
    valor_total,
    municipio_residencia,
    _ingerido_em,
    sk_estabelecimento,
    cod_regiao_saude,
    cod_uf,
    capitulo_cid,
    capitulo_nome,
    not cobre as cadastro_posterior
from pares
qualify row_number() over (
    partition by competencia, n_aih, dt_saida
    order by cobre desc, valido_de
) = 1
