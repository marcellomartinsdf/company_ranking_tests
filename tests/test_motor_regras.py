from __future__ import annotations

import unittest

from models import Inscricao
from services.motor_regras import MotorRegras


REGULAMENTO_TESTE = {
    "elegibilidade": [
        {
            "id": "aceite_regulamento",
            "nome": "Aceite do regulamento",
            "tipo": "equals",
            "campo": "aceite_regulamento",
            "valor_esperado": True,
            "politica_campo_ausente": "fail",
        }
    ],
    "pontuacao": {
        "nota_minima_classificacao": 20,
        "criterios": [
            {
                "id": "experiencia_exportadora",
                "nome": "Experiencia exportadora",
                "tipo": "range_score",
                "campo": "anos_experiencia_exportacao",
                "faixas": [
                    {"min": 5, "score": 20, "justificativa": "Faixa maxima."},
                    {"min": 0, "max_exclusive": 5, "score": 10, "justificativa": "Faixa intermediaria."}
                ],
            },
            {
                "id": "maturidade_exportadora",
                "nome": "Maturidade exportadora",
                "tipo": "value_map",
                "campo": "maturidade_exportadora",
                "mapa_valores": {"alta": 15, "media": 10},
                "revisao_humana": True,
                "contabilizar_sugestao_na_nota": True,
            }
        ],
    },
    "desempate": [],
}


class MotorRegrasTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.motor = MotorRegras(REGULAMENTO_TESTE)

    def test_deve_avaliar_e_somar_pontuacao_com_revisao_humana(self) -> None:
        inscricao = Inscricao.from_row(
            {
                "inscricao_id": "1",
                "empresa_nome": "Empresa A",
                "cnpj": "12345678000100",
                "aceite_regulamento": "Sim",
                "anos_experiencia_exportacao": "6",
                "maturidade_exportadora": "Alta",
            }
        )

        resultado = self.motor.avaliar(inscricao)

        self.assertTrue(resultado.elegivel)
        self.assertEqual(resultado.pontuacao_total, 35.0)
        self.assertTrue(resultado.nota_minima_atendida)
        self.assertTrue(resultado.revisao_humana_pendente)
        self.assertEqual(resultado.status_final, "classificada_com_revisao_pendente")

        criterio = resultado.obter_resultado_criterio("maturidade_exportadora")
        self.assertIsNotNone(criterio)
        self.assertEqual(criterio.pontuacao, 15.0)
        self.assertIn("revisao humana", criterio.justificativa.lower())

    def test_deve_eliminar_quando_nao_atende_criterio_eliminatorio(self) -> None:
        inscricao = Inscricao.from_row(
            {
                "inscricao_id": "2",
                "empresa_nome": "Empresa B",
                "aceite_regulamento": "Nao",
                "anos_experiencia_exportacao": "6",
            }
        )

        resultado = self.motor.avaliar(inscricao)

        self.assertFalse(resultado.elegivel)
        self.assertEqual(resultado.status_final, "eliminada")
        criterio = resultado.obter_resultado_criterio("aceite_regulamento")
        self.assertIsNotNone(criterio)
        self.assertEqual(criterio.resultado, "reprovado")
        self.assertTrue(criterio.justificativa)


if __name__ == "__main__":
    unittest.main()

