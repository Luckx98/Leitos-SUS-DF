"""CNES: estabelecimentos (ST) e leitos (LT), um arquivo por UF e competência."""

from __future__ import annotations

import re
from datetime import date

import psycopg

from loader.carga import Arquivo, Resultado
from loader.dbf import ler_dbc
from loader.versoes import deve_gravar_versao

_CNES = re.compile(r"[0-9]{7}")


def _flag(valor: str) -> bool | None:
    return {"1": True, "0": False}.get(valor)


def _ou_nulo(valor: str, nulos: tuple[str, ...] = ("",)) -> str | None:
    return None if valor in nulos else valor


def _limpo(valor: object) -> object:
    if not isinstance(valor, str):
        return valor
    texto = valor.strip()
    return texto or None


def _competencia_do_registro(registro: dict, arquivo: Arquivo) -> bool:
    competencia: date = arquivo.competencia  # type: ignore[assignment]
    return registro.get("COMPETEN") == f"{competencia:%Y%m}"


def processar_st(conexao: psycopg.Connection, id_carga: int, arquivo: Arquivo) -> tuple[Resultado, int]:
    resultado = Resultado()
    municipios = {linha[0] for linha in conexao.execute("SELECT cod_municipio FROM municipio")}
    por_cnes: dict[str, dict[date, tuple]] = {}
    for linha in conexao.execute(
        """
        SELECT cnes, competencia_inicio, cod_municipio, tipo_unidade, tipo_gestao,
               natureza_juridica, cnpj_mantenedora, vinculo_sus, atende_internacao, atende_urgencia
        FROM estabelecimento_versao
        """
    ):
        por_cnes.setdefault(linha[0].strip(), {})[linha[1]] = tuple(_limpo(valor) for valor in linha[2:])

    novos, versoes, vistos = [], [], set()
    for numero, registro in enumerate(ler_dbc(arquivo.caminho), start=1):
        resultado.linhas_lidas += 1
        cnes = registro["CNES"]
        if not _CNES.fullmatch(cnes):
            resultado.rejeitar(numero, "CNES inválido", registro)
            continue
        if cnes in vistos:
            resultado.rejeitar(numero, "CNES repetido no arquivo", registro)
            continue
        if registro["CODUFMUN"] not in municipios:
            resultado.rejeitar(numero, "município desconhecido", registro)
            continue
        if not registro["TP_UNID"] or not registro["TPGESTAO"]:
            resultado.rejeitar(numero, "tipo de unidade ou gestão vazio", registro)
            continue
        if not _competencia_do_registro(registro, arquivo):
            resultado.rejeitar(numero, "COMPETEN diferente da competência do arquivo", registro)
            continue
        vistos.add(cnes)

        atributos = (
            registro["CODUFMUN"],
            registro["TP_UNID"],
            registro["TPGESTAO"],
            _ou_nulo(registro.get("NAT_JUR", "")),
            _ou_nulo(registro.get("CNPJ_MAN", ""), ("", "00000000000000")),
            _flag(registro.get("VINC_SUS", "")),
            _flag(registro.get("ATENDHOS", "")),
            _flag(registro.get("URGEMERG", "")),
        )
        conhecidas = por_cnes.get(cnes)
        if conhecidas is None:
            novos.append((cnes, id_carga))
            conhecidas = {}
            por_cnes[cnes] = conhecidas
        if arquivo.competencia is None or not deve_gravar_versao(conhecidas, arquivo.competencia, atributos):
            continue
        versoes.append((cnes, arquivo.competencia, *atributos, id_carga))
        conhecidas[arquivo.competencia] = atributos

    with conexao.cursor() as cursor:
        if novos:
            with cursor.copy("COPY estabelecimento (cnes, primeira_carga) FROM STDIN") as copia:
                for linha in novos:
                    copia.write_row(linha)
        with cursor.copy(
            """
            COPY estabelecimento_versao (cnes, competencia_inicio, cod_municipio, tipo_unidade, tipo_gestao,
                natureza_juridica, cnpj_mantenedora, vinculo_sus, atende_internacao, atende_urgencia, id_carga)
            FROM STDIN
            """
        ) as copia:
            for linha in versoes:
                copia.write_row(linha)
    return resultado, len(novos) + len(versoes)


def processar_lt(conexao: psycopg.Connection, id_carga: int, arquivo: Arquivo) -> tuple[Resultado, int]:
    resultado = Resultado()
    conhecidos = {linha[0] for linha in conexao.execute("SELECT cnes FROM estabelecimento")}

    linhas, vistos = [], set()
    for numero, registro in enumerate(ler_dbc(arquivo.caminho), start=1):
        resultado.linhas_lidas += 1
        chave = (registro["CNES"], registro["CODLEITO"])
        if registro["CNES"] not in conhecidos:
            resultado.rejeitar(numero, "CNES sem cadastro (ST não carregado?)", registro)
            continue
        if not re.fullmatch(r"[0-9]{2}", registro["CODLEITO"]) or not re.fullmatch(r"[0-9]", registro["TP_LEITO"]):
            resultado.rejeitar(numero, "tipo ou código de leito inválido", registro)
            continue
        if chave in vistos:
            resultado.rejeitar(numero, "leito repetido no arquivo", registro)
            continue
        if not _competencia_do_registro(registro, arquivo):
            resultado.rejeitar(numero, "COMPETEN diferente da competência do arquivo", registro)
            continue
        try:
            quantidades = [int(registro[c] or 0) for c in ("QT_EXIST", "QT_CONTR", "QT_SUS", "QT_NSUS")]
        except ValueError:
            resultado.rejeitar(numero, "quantidade não numérica", registro)
            continue
        if min(quantidades) < 0:
            resultado.rejeitar(numero, "quantidade negativa", registro)
            continue
        vistos.add(chave)
        linhas.append((arquivo.competencia, *chave, registro["TP_LEITO"], *quantidades, id_carga))

    with conexao.cursor().copy(
        """
        COPY leito (competencia, cnes, cod_leito, tipo_leito, qt_existente, qt_contratado, qt_sus,
                    qt_nao_sus, id_carga)
        FROM STDIN
        """
    ) as copia:
        for linha in linhas:
            copia.write_row(linha)
    return resultado, len(linhas)
