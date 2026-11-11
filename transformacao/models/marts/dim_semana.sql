-- Uma linha por semana ISO e por UF, com a marca de mês provisório daquela UF.
select distinct
    semana,
    cod_uf,
    ano,
    mes,
    semana_iso,
    ano_iso,
    provisoria
from {{ ref('int_semana') }}
