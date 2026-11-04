-- Maturidade calculada pelo lote: provisório quando o mês de saída tem menos de 3 competências observadas.
select
    trim(uf) as uf,
    cast(mes_saida as date) as mes_saida,
    status
from {{ source('bronze', 'maturidade') }}
