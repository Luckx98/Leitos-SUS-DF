-- Índices da consulta otimizada. O par de planos (antes, sem estes índices,
-- e depois) é gerado por transformacao/explicar.py em medicoes/e3/.
CREATE INDEX IF NOT EXISTS idx_fato_internacao_cnes_saida
    ON consumo.fato_internacao (cnes, dt_saida)
    INCLUDE (capitulo_cid, dias_permanencia);

CREATE INDEX IF NOT EXISTS idx_ocupacao_regiao_ano
    ON consumo.ocupacao_semana_regiao (cod_regiao_saude, ano, semana)
    INCLUDE (ocupacao, acima_de_85);
