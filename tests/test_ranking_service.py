from __future__ import annotations

import unittest

from models import Inscricao
from services.motor_regras import MotorRegras
from services.ranking_service import RankingService


REGULAMENTO_TESTE = {
    "elegibilidade": [
        {
            "id": "aceite_regulamento",
            "tipo": "equals",
            "campo": "aceite_regulamento",
            "valor_esperado": True,
        }
    ],
    "pontuacao": {
        "nota_minima_classificacao": 10,
        "criterios": [
            {
                "id": "experiencia_exportadora",
                "tipo": "range_score",
                "campo": "anos_experiencia_exportacao",
                "faixas": [
                    {"min": 5, "score": 20},
                    {"min": 0, "max_exclusive": 5, "score": 10}
                ],
            }
        ],
    },
    "desempate": [
        {"tipo": "campo", "campo": "data_submissao", "ordem": "asc"}
    ],
}


class RankingServiceTestCase(unittest.TestCase):
    def test_deve_aplicar_desempate_por_data_submissao(self) -> None:
        motor = MotorRegras(REGULAMENTO_TESTE)
        ranking_service = RankingService(REGULAMENTO_TESTE)

        inscricao_a = Inscricao.from_row(
            {
                "inscricao_id": "1",
                "empresa_nome": "Empresa A",
                "aceite_regulamento": "Sim",
                "anos_experiencia_exportacao": "6",
                "data_submissao": "2026-03-20 10:00:00",
            }
        )
        inscricao_b = Inscricao.from_row(
            {
                "inscricao_id": "2",
                "empresa_nome": "Empresa B",
                "aceite_regulamento": "Sim",
                "anos_experiencia_exportacao": "6",
                "data_submissao": "2026-03-21 10:00:00",
            }
        )

        ranking = ranking_service.classificar([motor.avaliar(inscricao_b), motor.avaliar(inscricao_a)])

        self.assertEqual(ranking[0].inscricao.inscricao_id, "1")
        self.assertEqual(ranking[0].classificacao, 1)
        self.assertEqual(ranking[1].inscricao.inscricao_id, "2")
        self.assertEqual(ranking[1].classificacao, 2)


if __name__ == "__main__":
    unittest.main()

