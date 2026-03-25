from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.pipeline import executar_ranqueamento


class PipelineTestCase(unittest.TestCase):
    def test_deve_executar_pipeline_e_gerar_excel(self) -> None:
        with tempfile.TemporaryDirectory() as diretorio_temporario:
            base = Path(diretorio_temporario)
            entrada = base / "entrada.csv"
            saida = base / "resultado.xlsx"

            entrada.write_text(
                "\n".join(
                    [
                        "inscricao_id,empresa_nome,aceite_regulamento,situacao_cadastral,anos_experiencia_exportacao,quantidade_mercados_prioritarios,maturidade_exportadora",
                        "1,Empresa A,Sim,Ativa,6,3,Alta",
                        "2,Empresa B,Nao,Ativa,1,0,Baixa",
                    ]
                ),
                encoding="utf-8",
            )

            resumo = executar_ranqueamento(
                entrada,
                "config/regulamento_exemplo.json",
                saida,
            )

            self.assertEqual(resumo.total_inscricoes, 2)
            self.assertTrue(saida.exists())
            self.assertIn("classificada_com_revisao_pendente", resumo.contagem_status)


if __name__ == "__main__":
    unittest.main()
