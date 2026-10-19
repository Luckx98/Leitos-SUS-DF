# Leitos SUS-DF

## A capacidade de leitos acompanha a demanda?

O **Leitos SUS-DF** é a plataforma de dados do Grupo 01 de Banco de Dados 2 (UnB/FCTE, 2026/2). Ela cruza a capacidade de leitos do SUS (CNES) com a demanda por internação (SIH/SUS) para mostrar onde e quando a ocupação passa do limite, no Distrito Federal e em Goiás.

## Problema

Capacidade e demanda são acompanhadas em sistemas separados. A falta de leito, principalmente nos picos sazonais (doenças respiratórias no inverno, dengue no verão), só é percebida quando já está acontecendo.

## Pergunta de gestão

> Entre 2021 e 2025, em quais semanas do ano a ocupação estimada de leitos SUS (paciente-dia ÷ leitos cadastrados) ultrapassou 85% em cada região de saúde do DF, e quais causas de internação (CID) concentravam esse excesso?

**Persona:** gestor da Secretaria de Saúde do DF e da Central de Regulação de Leitos.

## Fontes

| Fonte | Conteúdo |
| --- | --- |
| SIH/SUS (AIH reduzida) | uma linha por internação paga pelo SUS, publicada mensalmente |
| CNES (estabelecimentos e leitos) | cadastro de estabelecimentos e leitos por tipo, retrato mensal |
| Tabelas auxiliares do DATASUS | CID-10, municípios e regiões de saúde |

Os dados vêm do FTP público do DATASUS e do Portal de Dados Abertos do SUS, sob licença Creative Commons Atribuição-SemDerivações 3.0.

## Pipeline de dados

![Pipeline: fontes, migrações, carga, banco de origem, lote e CDC até o lakehouse](pipeline.svg)

- **FONTES:** arquivos públicos do DATASUS com as internações (SIH/SUS) e os estabelecimentos e leitos (CNES) do DF e de Goiás, de 2021 até a última competência publicada, mais as tabelas de CID-10, municípios e regiões de saúde. Um recorte versionado no repositório permite subir a plataforma sem rede.
- **MIGRAÇÕES:** o Docker Compose sobe o PostgreSQL e cria o esquema a partir de um banco vazio, em ordem, antes de qualquer carga.
- **CARGA:** o loader baixa os arquivos, valida cada linha e grava um arquivo por transação. Arquivos já carregados são ignorados, então a carga pode ser repetida ou retomada; linhas inválidas ficam registradas com o motivo.
- **BANCO DE ORIGEM:** PostgreSQL insert-only, que nunca sobrescreve: guarda as versões do cadastro, os leitos mês a mês e, em cada internação, a data do evento, a competência e a data de carga. Sobe pronto para a captura de mudanças (`wal_level=logical`), usada a partir daqui (E2).
- **LOTE:** exportação incremental da origem para o lakehouse, por marca d'água de carga, com reprocessamento da janela de dado atrasado. [Mais detalhes](e2/01-lote-incremental.md).
- **CDC:** Debezium lê o WAL lógico e publica no Redpanda; um consumidor Python grava no Iceberg com latência de segundos. [Mais detalhes](e2/02-cdc.md).
- **LAKEHOUSE (ICEBERG):** os dois caminhos escrevem o mesmo esquema, em namespaces separados, para serem reconciliados e comparados. Toda escrita cria um snapshot novo; os anteriores continuam acessíveis, o que permite consultar — ou voltar a tabela inteira (`rollback`) — a um estado passado, sem uma tabela de histórico separada. É o que [a demonstração da semântica de entrega](e2/04-semantica-de-entrega.md) usa para restaurar `cdc.*` depois de uma releitura sem deduplicação. Decisão e medições no [ADR 0002](adr/0002-lote-incremental-e-cdc-sobre-iceberg.md).


## Executar

```bash
git clone https://github.com/Luckx98/Leitos-SUS-DF.git
cd Leitos-SUS-DF
docker compose up --build
```

O README do repositório traz o modo de carga completa, as consultas de verificação e os testes.

## Equipe

| Nome | Matrícula |
| --- | --- |
| Lucas Macedo Barboza | 190091720 |
| Caetano Santos Lucio | 180144979 |
| Cairo Florenço | 222014975 |
| Leonardo Sobrinho | 200022199 |
| Carlos Eduardo Mendes de Mesquita | 190085584 |
| Bruna de Lima | 211041105 |
| Lais Cecília | 211029512 |

O código-fonte está no [repositório do projeto](https://github.com/Luckx98/Leitos-SUS-DF).
