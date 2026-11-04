-- Opção nula da E3: a pergunta de gestão calculada direto na origem.
-- É o que um cron com script SQL rodaria. Usa a versão mais recente do
-- cadastro (DISTINCT ON ... competencia_inicio DESC), não a versão vigente
-- na data da saída. Sem camada, sem teste e sem grafo.
-- Ocupação = paciente-dia da semana ÷ (leitos SUS da competência × 7).
WITH regiao AS (
    SELECT DISTINCT ON (v.cnes) v.cnes,
           CASE WHEN v.cod_municipio = '530010' THEN df.cod_regiao_saude ELSE m.cod_regiao_saude END AS cod_regiao_saude
    FROM estabelecimento_versao v
    JOIN municipio m USING (cod_municipio)
    LEFT JOIN estabelecimento_regiao_df df USING (cnes)
    ORDER BY v.cnes, v.competencia_inicio DESC
),
paciente_dia AS (
    SELECT r.cod_regiao_saude, date_trunc('week', d.dia)::date AS semana, count(*) AS paciente_dias
    FROM internacao_vigente i
    JOIN regiao r USING (cnes)
    CROSS JOIN LATERAL generate_series(
        i.dt_saida - i.dias_permanencia, i.dt_saida - 1, interval '1 day'
    ) AS d(dia)
    WHERE i.dias_permanencia > 0
      AND r.cod_regiao_saude IS NOT NULL
    GROUP BY 1, 2
),
leitos AS (
    SELECT r.cod_regiao_saude, l.competencia, sum(l.qt_sus) AS leitos_sus
    FROM leito_vigente l
    JOIN regiao r USING (cnes)
    WHERE r.cod_regiao_saude IS NOT NULL
    GROUP BY 1, 2
)
SELECT rs.cod_uf, rs.nome AS regiao_saude, p.semana, p.paciente_dias, l.leitos_sus,
       round(p.paciente_dias / (l.leitos_sus * 7.0), 3) AS ocupacao
FROM paciente_dia p
JOIN leitos l
  ON l.cod_regiao_saude = p.cod_regiao_saude
 AND l.competencia = date_trunc('month', p.semana)::date
JOIN regiao_saude rs ON rs.cod_regiao_saude = p.cod_regiao_saude
WHERE l.leitos_sus > 0
ORDER BY rs.cod_uf DESC, rs.nome, p.semana
