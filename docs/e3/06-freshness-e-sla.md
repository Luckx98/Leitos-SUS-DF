# Freshness e SLA

A tabela de consumo é `consumo.ocupacao_semana_regiao`.

**SLA:** ela reflete o lote em até 24 horas. A agenda diária das 06:00 reconstrói os marts. A declaração versionada está em `transformacao/models/marts/sla.sql` e é publicada em `consumo.sla`.

Cada linha do mart carrega `construida_em`. A publicação grava `consumo.controle_freshness` com:

- `construida_em` — quando o mart foi construído;
- `ingerido_em` — o `_ingerido_em` máximo de `lote.internacao`, lido pela staging;
- `atraso_horas` — de `construida_em` até o instante da publicação;
- `dentro_do_sla` — atraso de no máximo 24 horas e mart não anterior ao lote.

O teste `teste_freshness_sla` falha se o mart foi construído mais de uma hora antes da ingestão, ou se `construida_em` tem mais de 24 horas. Uma hora de folga cobre o relógio entre o lote e o dbt; o limite de 24 horas é o SLA.

O painel mostra a frase de freshness e marca a semana como provisória quando `lote.maturidade` (ou, na falta dela, a distância até a competência mais recente do SIH) diz que o mês ainda não teve três competências observadas. A regra é a da E1: 99,5% das AIHs chegam em até três competências.
