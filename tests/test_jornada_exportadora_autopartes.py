from __future__ import annotations

import unittest

from models import Inscricao
from services.motor_regras import MotorRegras
from services.ranking_service import RankingService


REGULAMENTO_JORNADA_TESTE = {
    "elegibilidade": [
        {
            "id": "setor_autopartes",
            "tipo": "equals",
            "campo": "setor_classificacao",
            "valor_esperado": "Classificada",
        },
        {
            "id": "perfil_publico_alvo",
            "tipo": "equals",
            "campo": "classificacao_porte_maturidade",
            "valor_esperado": "Perfil aderente",
        },
        {
            "id": "pendencia_financeira_apex",
            "tipo": "equals",
            "campo": "possui_pendencia_financeira_apex",
            "valor_esperado": False,
            "politica_campo_ausente": "review",
            "aprovar_provisoriamente_quando_pendente": True,
        },
    ],
    "pontuacao": {
        "nota_minima_classificacao": 5,
        "criterios": [
            {
                "id": "atendimento_peiex",
                "tipo": "binary_score",
                "campo": "participa_peiex",
                "campo_score_override": "pontuacao_peiex_legado",
                "pontuacao": 1,
            },
            {
                "id": "atendimento_consultoria_sebrae",
                "tipo": "binary_score",
                "campo": "participa_consultoria_sebrae_exportacao",
                "campo_score_override": "pontuacao_consultoria_sebrae_legado",
                "pontuacao": 1,
            },
            {
                "id": "website_ou_rede_social",
                "tipo": "binary_score",
                "campo": "website_ou_rede_social_verificado",
                "campo_score_override": "pontuacao_website_legado",
                "pontuacao": 1,
            },
            {
                "id": "website_lingua_estrangeira",
                "tipo": "binary_score",
                "campo": "website_internacional_verificado",
                "campo_score_override": "pontuacao_website_internacional_legado",
                "pontuacao": 1,
            },
            {
                "id": "catalogo_digital_idioma_estrangeiro",
                "tipo": "binary_score",
                "campo": "material_promocional_idioma_estrangeiro",
                "campo_score_override": "pontuacao_catalogo_digital_legado",
                "pontuacao": 1,
            },
            {
                "id": "lideranca_feminina",
                "tipo": "binary_score",
                "campo": "liderada_por_mulher",
                "campo_score_override": "pontuacao_lideranca_feminina_legado",
                "pontuacao": 1,
            },
            {
                "id": "lideranca_racial",
                "tipo": "binary_score",
                "campo": "liderada_por_pessoa_negra",
                "campo_score_override": "pontuacao_lideranca_racial_legado",
                "pontuacao": 1,
            },
            {
                "id": "diversidade_regional",
                "tipo": "binary_score",
                "campo": "diversidade_regional",
                "campo_score_override": "pontuacao_diversidade_regional_legado",
                "pontuacao": 1,
            },
        ],
    },
    "analise_demanda": [
        {
            "id": "demanda_mercado_alvo",
            "tipo": "gte",
            "campo": "numero_compradores_interessados",
            "valor_minimo": 1,
            "politica_campo_ausente": "review",
            "aprovar_provisoriamente_quando_pendente": True,
        }
    ],
    "desempate": [
        {"tipo": "criterio", "criterio_id": "atendimento_peiex", "ordem": "desc"},
        {
            "tipo": "soma_criterios",
            "criterios": [
                "website_ou_rede_social",
                "website_lingua_estrangeira",
                "catalogo_digital_idioma_estrangeiro",
            ],
            "ordem": "desc",
        },
        {
            "tipo": "soma_criterios",
            "criterios": ["lideranca_feminina", "lideranca_racial"],
            "ordem": "desc",
        },
        {"tipo": "criterio", "criterio_id": "diversidade_regional", "ordem": "desc"},
        {"tipo": "campo", "campo": "data_submissao", "ordem": "asc"},
    ],
}


class JornadaExportadoraAutopartesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.motor = MotorRegras(REGULAMENTO_JORNADA_TESTE)
        self.ranking_service = RankingService(REGULAMENTO_JORNADA_TESTE)

    def test_deve_usar_pontuacoes_legadas_da_planilha_atual(self) -> None:
        inscricao = Inscricao.from_row(
            {
                "inscricao_id": "1",
                "empresa_nome": "Empresa A",
                "setor_classificacao": "Classificada",
                "classificacao_porte_maturidade": "Perfil aderente",
                "pontuacao_peiex_legado": 1,
                "pontuacao_consultoria_sebrae_legado": 0,
                "pontuacao_website_legado": 1,
                "pontuacao_website_internacional_legado": 1,
                "pontuacao_catalogo_digital_legado": 1,
                "pontuacao_lideranca_feminina_legado": 1,
                "pontuacao_lideranca_racial_legado": 0,
                "pontuacao_diversidade_regional_legado": 0,
            }
        )

        resultado = self.motor.avaliar(inscricao)

        self.assertTrue(resultado.elegivel)
        self.assertEqual(resultado.pontuacao_total, 5.0)
        self.assertEqual(resultado.status_final, "aguardando_analise_de_demanda")
        self.assertTrue(resultado.demanda_pendente_revisao)
        criterio = resultado.obter_resultado_criterio("atendimento_peiex")
        self.assertIsNotNone(criterio)
        self.assertIn("planilha atual", criterio.justificativa.lower())

    def test_deve_desempatar_por_grupo_de_marketing(self) -> None:
        inscricao_a = Inscricao.from_row(
            {
                "inscricao_id": "1",
                "empresa_nome": "Empresa A",
                "data_submissao": "2026-01-20 10:00:00",
                "setor_classificacao": "Classificada",
                "classificacao_porte_maturidade": "Perfil aderente",
                "numero_compradores_interessados": 2,
                "pontuacao_peiex_legado": 0,
                "pontuacao_consultoria_sebrae_legado": 0,
                "pontuacao_website_legado": 1,
                "pontuacao_website_internacional_legado": 1,
                "pontuacao_catalogo_digital_legado": 1,
                "pontuacao_lideranca_feminina_legado": 1,
                "pontuacao_lideranca_racial_legado": 0,
                "pontuacao_diversidade_regional_legado": 1,
            }
        )
        inscricao_b = Inscricao.from_row(
            {
                "inscricao_id": "2",
                "empresa_nome": "Empresa B",
                "data_submissao": "2026-01-19 10:00:00",
                "setor_classificacao": "Classificada",
                "classificacao_porte_maturidade": "Perfil aderente",
                "numero_compradores_interessados": 2,
                "pontuacao_peiex_legado": 0,
                "pontuacao_consultoria_sebrae_legado": 0,
                "pontuacao_website_legado": 1,
                "pontuacao_website_internacional_legado": 0,
                "pontuacao_catalogo_digital_legado": 0,
                "pontuacao_lideranca_feminina_legado": 1,
                "pontuacao_lideranca_racial_legado": 1,
                "pontuacao_diversidade_regional_legado": 1,
            }
        )

        ranking = self.ranking_service.classificar(
            [self.motor.avaliar(inscricao_b), self.motor.avaliar(inscricao_a)]
        )

        self.assertEqual(ranking[0].inscricao.inscricao_id, "1")
        self.assertEqual(ranking[0].classificacao, 1)
        self.assertEqual(ranking[1].inscricao.inscricao_id, "2")


if __name__ == "__main__":
    unittest.main()
