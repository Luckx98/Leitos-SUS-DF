import unittest
from datetime import date

from semantico.frases import chave, frase, resumir


class TestFrases(unittest.TestCase):
    def test_frase_carrega_o_numero_do_mart_e_o_limiar_em_palavras(self):
        texto = frase(
            {
                "nome_regiao": "Central",
                "semana": date(2025, 1, 6),
                "ocupacao": 1.1429,
                "acima_de_85": True,
                "leitos_sus": 10,
                "paciente_dias": 80,
                "capitulo_nome": "Doenças do aparelho respiratório",
                "parcela": 1,
            }
        )
        self.assertIn("Central", texto)
        self.assertIn("06/01/2025", texto)
        self.assertIn("114%", texto)
        self.assertIn("10 leitos", texto)
        self.assertIn("80 paciente-dias", texto)
        self.assertIn("Doenças do aparelho respiratório", texto)
        self.assertIn("passou de 85%", texto)
        self.assertNotIn("não passou", texto)

    def test_frase_abaixo_do_limiar_nao_diz_que_passou(self):
        texto = frase(
            {
                "nome_regiao": "Sul",
                "semana": "2025-07-07",
                "ocupacao": 0.4,
                "acima_de_85": False,
                "leitos_sus": 20,
                "paciente_dias": 56,
                "capitulo_nome": None,
                "parcela": None,
            }
        )
        self.assertIn("não passou de 85%", texto)
        self.assertIn("causa não classificada", texto)
        self.assertIn("40%", texto)

    def test_cosseno_e_limiar_nao_sao_o_mesmo_conjunto(self):
        acima = {chave("53002", date(2025, 1, 6)), chave("53003", date(2025, 1, 13))}
        topo = [
            {"cod_regiao_saude": "53002", "semana": date(2025, 1, 6)},
            {"cod_regiao_saude": "53008", "semana": date(2025, 7, 7)},
        ]
        conta = resumir(topo, acima)
        self.assertEqual(conta["no_topo_e_acima"], 1)
        self.assertEqual(conta["no_topo_abaixo"], 1)
        self.assertEqual(conta["acima_fora_do_topo"], 1)
        self.assertEqual(conta["acima_no_total"], 2)


if __name__ == "__main__":
    unittest.main()
