-- Cada AIH da carga vigente encontra exatamente uma versão do estabelecimento.
select s.competencia, s.n_aih, s.dt_saida, count(i.n_aih) as versoes
from {{ ref('stg_internacao') }} as s
left join {{ ref('int_internacao') }} as i
    on i.competencia = s.competencia
   and i.n_aih = s.n_aih
   and i.dt_saida = s.dt_saida
group by s.competencia, s.n_aih, s.dt_saida
having count(i.n_aih) <> 1
