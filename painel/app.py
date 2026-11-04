"""Painel da pergunta de gestão: semanas acima de 85% e as causas desse excesso."""

from __future__ import annotations

import os
from datetime import date

import altair as alt
import pandas as pd
import psycopg
import streamlit as st

st.set_page_config(page_title="Leitos SUS-DF", layout="wide")


def _consultar(sql: str, parametros: tuple = ()) -> pd.DataFrame:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conexao, conexao.cursor() as cursor:
        cursor.execute(sql, parametros)
        colunas = [item.name for item in cursor.description]
        return pd.DataFrame(cursor.fetchall(), columns=colunas)


@st.cache_data(ttl=300)
def carregar(uf: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ocupacao = _consultar(
        """
        SELECT r.nome AS regiao, o.cod_regiao_saude, o.semana, o.ano, o.paciente_dias,
               o.leitos_sus, o.ocupacao, o.acima_de_85, o.provisoria
        FROM consumo.ocupacao_semana_regiao o
        JOIN consumo.dim_regiao_saude r USING (cod_regiao_saude)
        WHERE r.cod_uf = %s
        ORDER BY o.semana, r.nome
        """,
        (uf,),
    )
    causas = _consultar(
        """
        SELECT o.cod_regiao_saude, c.semana, c.capitulo_cid, c.capitulo_nome,
               c.paciente_dias, c.parcela
        FROM consumo.causa_semana_regiao c
        JOIN consumo.ocupacao_semana_regiao o USING (cod_regiao_saude, semana)
        JOIN consumo.dim_regiao_saude r ON r.cod_regiao_saude = o.cod_regiao_saude
        WHERE o.acima_de_85 AND r.cod_uf = %s
        """,
        (uf,),
    )
    freshness = _consultar(
        """
        SELECT construida_em, atraso_horas, sla_horas, dentro_do_sla
        FROM consumo.controle_freshness
        WHERE tabela = 'ocupacao_semana_regiao'
        """
    )
    return ocupacao, causas, freshness


st.title("Ocupação de leitos SUS")
st.caption(
    "Em quais semanas a ocupação estimada (paciente-dia ÷ leitos SUS × 7) passou de 85% "
    "em cada região de saúde, e quais capítulos da CID concentravam esse excesso."
)

uf_nome = st.radio("UF", ["Distrito Federal", "Goiás"], horizontal=True)
uf = "53" if uf_nome.startswith("Distrito") else "52"

try:
    ocupacao, causas, freshness = carregar(uf)
except psycopg.Error as erro:
    st.error(f"O schema consumo ainda não está publicado ({erro}).")
    st.stop()

if ocupacao.empty:
    st.warning("Não há semanas com leito SUS para esta UF no recorte carregado.")
    st.stop()

ocupacao["semana"] = pd.to_datetime(ocupacao["semana"])
if not causas.empty:
    causas["semana"] = pd.to_datetime(causas["semana"])

if (ocupacao["semana"].max() - ocupacao["semana"].min()).days < 40:
    st.info(
        "Este recorte é a amostra versionada (uma competência, sem rede). "
        "A série de 2021 a 2025 sobe com MODO=completo."
    )

if not freshness.empty:
    linha = freshness.iloc[0]
    construida = linha["construida_em"]
    texto = f"Tabela de consumo construída em {construida}. SLA de {int(linha['sla_horas'])} horas."
    if bool(linha["dentro_do_sla"]):
        st.success(texto)
    else:
        st.warning(texto + " Fora do SLA.")

regioes = ["Todas"] + sorted(ocupacao["regiao"].unique())
escolha = st.selectbox("Região de saúde", regioes)
recorte = ocupacao if escolha == "Todas" else ocupacao[ocupacao["regiao"] == escolha]
excesso = recorte[recorte["acima_de_85"]]

colunas = st.columns(3)
colunas[0].metric("Semanas no recorte", f"{recorte['semana'].nunique()}")
colunas[1].metric("Semanas acima de 85%", f"{excesso['semana'].nunique()}")
pico = recorte["ocupacao"].max()
colunas[2].metric("Maior ocupação", "—" if pd.isna(pico) else f"{pico:.0%}")

if recorte["provisoria"].any():
    st.caption(
        "Semanas marcadas como provisórias: a AIH desse mês ainda pode chegar "
        "(menos de 3 competências observadas)."
    )

serie = (
    alt.Chart(recorte)
    .mark_line(point=True)
    .encode(
        x=alt.X("semana:T", title="Semana"),
        y=alt.Y("ocupacao:Q", title="Ocupação", axis=alt.Axis(format="%")),
        color=alt.Color("regiao:N", title="Região"),
        tooltip=["regiao", "semana", alt.Tooltip("ocupacao:Q", format=".1%"), "paciente_dias", "leitos_sus"],
    )
)
limite = alt.Chart(pd.DataFrame({"ocupacao": [0.85]})).mark_rule(
    strokeDash=[6, 4], color="#b45309"
).encode(y="ocupacao:Q")
st.altair_chart(serie + limite, use_container_width=True)

st.subheader("Semanas acima de 85%")
if excesso.empty:
    st.write("Nenhuma semana deste recorte passou de 85%.")
else:
    tabela = excesso.copy()
    tabela["ocupação"] = tabela["ocupacao"].map(lambda valor: f"{valor:.0%}")
    tabela["situação"] = tabela["provisoria"].map(lambda valor: "provisória" if valor else "madura")
    st.dataframe(
        tabela[["regiao", "semana", "ocupação", "paciente_dias", "leitos_sus", "situação"]],
        hide_index=True,
        use_container_width=True,
    )

st.subheader("Capítulos da CID nesse excesso")
causas_recorte = causas
if escolha != "Todas" and not causas.empty:
    codigo = recorte["cod_regiao_saude"].iloc[0]
    causas_recorte = causas[causas["cod_regiao_saude"] == codigo]
if causas_recorte.empty:
    st.write("Sem semanas acima de 85%, não há excesso para abrir por causa.")
else:
    resumo = (
        causas_recorte.groupby("capitulo_nome", as_index=False)["paciente_dias"].sum()
        .sort_values("paciente_dias", ascending=False)
    )
    barras = (
        alt.Chart(resumo)
        .mark_bar(color="#0c3b2b")
        .encode(
            x=alt.X("paciente_dias:Q", title="Paciente-dia"),
            y=alt.Y("capitulo_nome:N", sort="-x", title=None),
            tooltip=["capitulo_nome", "paciente_dias"],
        )
    )
    st.altair_chart(barras, use_container_width=True)

st.caption(f"Consulta em {date.today():%d/%m/%Y}. Fonte: SIH/SUS e CNES, agregados no schema consumo.")
