import unittest
from datetime import date

from loader.versoes import deve_gravar_versao

ATRIBUTOS = ("530010", "05", "M", None, None, True, True, False)
OUTROS = ("530010", "05", "E", None, None, True, True, False)


class TestVersaoAnterior(unittest.TestCase):
    def test_primeira_versao_entra_mesmo_com_uma_futura_igual(self):
        por_inicio = {date(2025, 1, 1): ATRIBUTOS}
        self.assertTrue(deve_gravar_versao(por_inicio, date(2021, 1, 1), ATRIBUTOS))

    def test_mes_que_ja_existe_nao_entra(self):
        por_inicio = {date(2021, 1, 1): ATRIBUTOS}
        self.assertFalse(deve_gravar_versao(por_inicio, date(2021, 1, 1), OUTROS))

    def test_sem_mudanca_desde_a_anterior_nao_entra(self):
        por_inicio = {date(2021, 1, 1): ATRIBUTOS, date(2025, 1, 1): OUTROS}
        self.assertFalse(deve_gravar_versao(por_inicio, date(2022, 6, 1), ATRIBUTOS))

    def test_mudanca_desde_a_anterior_entra(self):
        por_inicio = {date(2021, 1, 1): ATRIBUTOS}
        self.assertTrue(deve_gravar_versao(por_inicio, date(2023, 4, 1), OUTROS))
