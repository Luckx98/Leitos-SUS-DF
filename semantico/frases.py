"""Frase que o warehouse já sabe dizer, e a conta que compara o top-k com o limiar."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

# As três perguntas do experimento. A terceira repete as palavras do indicador
# de propósito: o cosseno olha o texto, não a coluna `acima_de_85`.
PERGUNTAS = (
    "pico de causa respiratória",
    "falta de leito no inverno",
    "semana em que a ocupação passou de 85%",
)

TOPO = 5


def chave(cod_regiao_saude: Any, semana: Any) -> tuple[str, str]:
    if isinstance(semana, datetime):
        semana = semana.date()
    if isinstance(semana, date):
        semana = semana.isoformat()
    return str(cod_regiao_saude), str(semana)[:10]


def frase(linha: dict) -> str:
    """Uma frase por região e semana. O número vem do mart; o vetor não recalcula."""
    semana = linha["semana"]
    if isinstance(semana, datetime):
        semana = semana.date()
    if isinstance(semana, date):
        semana_txt = f"{semana:%d/%m/%Y}"
    else:
        semana_txt = str(semana)[:10]

    ocupacao = float(linha["ocupacao"])
    marca = "passou" if linha["acima_de_85"] else "não passou"
    capitulo = linha.get("capitulo_nome") or "causa não classificada"
    parcela = linha.get("parcela")
    if parcela is None:
        causa = f"A causa que mais concentrou os paciente-dias foi {capitulo}."
    else:
        causa = (
            f"A causa que mais concentrou os paciente-dias foi {capitulo} "
            f"({float(parcela):.0%} da semana)."
        )
    return (
        f"Na região {linha['nome_regiao']}, na semana de {semana_txt}, "
        f"a ocupação estimada de leitos SUS foi de {ocupacao:.0%}, "
        f"com {int(linha['leitos_sus'])} leitos cadastrados e "
        f"{int(linha['paciente_dias'])} paciente-dias. "
        f"{causa} A ocupação {marca} de 85%."
    )


def resumir(topo: list[dict], acima: set[tuple[str, str]]) -> dict[str, int]:
    """Quantos do top-k também passaram de 85%, e quantos do limiar ficaram de fora."""
    chaves = {chave(item["cod_regiao_saude"], item["semana"]) for item in topo}
    return {
        "no_topo": len(chaves),
        "no_topo_e_acima": sum(1 for item in chaves if item in acima),
        "no_topo_abaixo": sum(1 for item in chaves if item not in acima),
        "acima_fora_do_topo": sum(1 for item in acima if item not in chaves),
        "acima_no_total": len(acima),
    }
