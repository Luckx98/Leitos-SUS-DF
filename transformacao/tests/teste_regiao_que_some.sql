-- Região de saúde do DF que tinha leito no primeiro ano da série e some no último.
-- Com um ano só (a amostra) não há o que comparar, e o teste passa vazio.
with anos as (
    select cod_regiao_saude, ano
    from {{ ref('ocupacao_semana_regiao') }}
    where cod_uf = '53'
    group by 1, 2
),
extremos as (
    select min(ano) as primeiro, max(ano) as ultimo from anos
)
select r.cod_regiao_saude, r.nome
from {{ ref('dim_regiao_saude') }} as r
cross join extremos as e
where r.cod_uf = '53'
  and e.ultimo > e.primeiro
  and exists (
      select 1 from anos as a
      where a.cod_regiao_saude = r.cod_regiao_saude and a.ano = e.primeiro
  )
  and not exists (
      select 1 from anos as a
      where a.cod_regiao_saude = r.cod_regiao_saude and a.ano = e.ultimo
  )
