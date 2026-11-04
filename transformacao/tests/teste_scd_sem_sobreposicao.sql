-- Vigências do mesmo CNES não se sobrepõem. É o que pega a dimensão tratada como sobrescrita.
select a.cnes, a.valido_de, b.valido_de as outra
from {{ ref('dim_estabelecimento') }} as a
inner join {{ ref('dim_estabelecimento') }} as b
    on a.cnes = b.cnes
   and a.sk_estabelecimento < b.sk_estabelecimento
   and a.valido_de < b.valido_ate_exclusivo
   and b.valido_de < a.valido_ate_exclusivo
