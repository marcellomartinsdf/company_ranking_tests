from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from services.carregador_config import carregar_regulamento
from services.carregador_inscricoes import carregar_inscricoes
from services.motor_regras import MotorRegras
from services.verificacao_automatica import VerificacaoAutomaticaService


class RegulamentoConstrucaoTestCase(unittest.TestCase):
    def test_deve_pontuar_criterios_do_regulamento_com_headers_do_formulario(self) -> None:
        regulamento_path = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "regulamento_exporta_mais_brasil_construcao_2026.json"
        )
        regulamento = carregar_regulamento(regulamento_path)

        with tempfile.TemporaryDirectory() as diretorio_temporario:
            caminho = Path(diretorio_temporario) / "construcao.xlsx"
            workbook = Workbook()
            worksheet = workbook.active
            worksheet.title = "Ranqueamento"
            worksheet.append(
                [
                    "Inscrição (Código)",
                    "Nome Fantasia",
                    "CNPJ",
                    "Setor de Atuação Primário",
                    "CNAE Primário",
                    "Sua empresa exportou diretamente ou indiretamente nos últimos 2 anos? (C011)",
                    "Por gentileza, indique o perfil da sua empresa: (C012)",
                    "A empresa é gerenciada ou controlada por mulher?",
                    "Sua empresa já foi atendida pelo PEIEX ou agroBR? (C023)",
                    "Catálogo em idioma estrangeiro. (1 ponto) (C021)",
                    "Informe os produtos (SH6/NCM e descrição) que a empresa pretende exportar nesta rodada de negócios: (C005)",
                    "Informe o link da pasta para download com o catálogo ou folder: (C106)",
                ]
            )
            worksheet.append(
                [
                    "INS-1",
                    "Empresa Construção",
                    "12.345.678/0001-95",
                    "CASA E CONSTRUÇÃO",
                    "2512-8 - Fabricação de esquadrias de metal",
                    "Sim",
                    "Empresa brasileira que exporta diretamente",
                    "Sim",
                    "Sim",
                    "Sim",
                    "7610.10.00",
                    "https://example.com/catalogo.pdf",
                ]
            )
            workbook.save(caminho)
            workbook.close()

            inscricoes = carregar_inscricoes(
                caminho,
                sheet_name=regulamento["origem_dados"]["sheet_name"],
                field_map=regulamento["origem_dados"]["mapeamento_campos"],
            )
            inscricoes = VerificacaoAutomaticaService(regulamento).enriquecer_inscricoes(inscricoes)

            self.assertEqual(len(inscricoes), 1)
            inscricao = inscricoes[0]
            self.assertIs(inscricao.obter_campo("perfil_setor_construcao_aderente"), True)
            self.assertIs(inscricao.obter_campo("empresa_exportadora"), True)
            self.assertIs(inscricao.obter_campo("exportou_diretamente_ultimos_2_anos"), True)
            self.assertIs(inscricao.obter_campo("liderada_por_mulher"), True)
            self.assertIs(inscricao.obter_campo("participa_peiex"), True)
            self.assertIs(inscricao.obter_campo("material_promocional_idioma_estrangeiro"), True)

            resultado = MotorRegras(regulamento).avaliar(inscricao)
            self.assertEqual(resultado.pontuacao_total, 5.0)
            self.assertEqual(
                resultado.obter_resultado_criterio("criterio_a_exportacao_direta").pontuacao,
                2.0,
            )
            self.assertEqual(
                resultado.obter_resultado_criterio("criterio_b_lideranca_feminina").pontuacao,
                1.0,
            )
            self.assertEqual(
                resultado.obter_resultado_criterio("criterio_c_peiex").pontuacao,
                1.0,
            )
            self.assertEqual(
                resultado.obter_resultado_criterio(
                    "criterio_e_material_promocional_idioma_estrangeiro"
                ).pontuacao,
                1.0,
            )


if __name__ == "__main__":
    unittest.main()
