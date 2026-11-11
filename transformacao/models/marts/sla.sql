-- SLA da tabela de consumo que responde à pergunta de gestão.
select
    'ocupacao_semana_regiao' as tabela,
    24 as sla_horas,
    'A ocupação semanal reflete o lote em até 24 horas. A agenda diária, às 06:00, reconstrói os marts.' as descricao
