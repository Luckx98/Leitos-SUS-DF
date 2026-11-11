"""Decide se um mês do CNES-ST vira uma versão nova do estabelecimento."""

from __future__ import annotations

from datetime import date


def deve_gravar_versao(por_inicio: dict[date, tuple], competencia: date, atributos: tuple) -> bool:
    """Grava quando o mês ainda não existe e os atributos mudaram desde a versão anterior.

    A amostra de 01/2025 pode ter entrado antes do histórico. Uma versão posterior
    não cobre os meses anteriores: sem a versão de 2021, o leito daquele mês fica
    sem cadastro. Se não há versão anterior, esta é a primeira e entra mesmo que
    uma versão futura tenha os mesmos atributos.
    """
    if competencia in por_inicio:
        return False
    anteriores = [inicio for inicio in por_inicio if inicio < competencia]
    if not anteriores:
        return True
    return por_inicio[max(anteriores)] != atributos
