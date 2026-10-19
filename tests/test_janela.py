import unittest
from datetime import date

from lakehouse.janela import meses_entre, somar_meses, status


class TestJanela(unittest.TestCase):
    def test_aritmetica_de_meses(self):
        self.assertEqual(somar_meses(date(2025, 2, 1), -3), date(2024, 11, 1))
        self.assertEqual(somar_meses(date(2025, 12, 1), 1), date(2026, 1, 1))
        self.assertEqual(meses_entre(date(2024, 11, 1), date(2025, 2, 1)), 3)

    def test_maturidade_de_tres_competencias(self):
        self.assertEqual(status(2), "provisório")
        self.assertEqual(status(3), "maduro")
        self.assertEqual(status(0), "provisório")


if __name__ == "__main__":
    unittest.main()
