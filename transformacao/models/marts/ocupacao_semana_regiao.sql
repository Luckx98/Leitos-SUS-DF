-- Uma linha por região de saúde por semana ISO.
-- Ocupação = paciente-dia ÷ (leitos SUS × 7). Acima de 85% é a pergunta da E1.
select
    cod_regiao_saude,
    cod_uf,
    semana,
    ano,
    mes,
    semana_iso,
    ano_iso,
    leitos_sus,
    paciente_dias,
    ocupacao,
    acima_de_85,
    provisoria,
    current_timestamp as construida_em
from {{ ref('int_semana') }}
where true
{{ filtrar_anos('semana') }}
