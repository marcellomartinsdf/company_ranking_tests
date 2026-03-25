from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.regulamento_documental import preparar_regulamento_documental


class RegulamentoDocumentalTestCase(unittest.TestCase):
    def test_deve_aproveitar_regulamento_preset_compativel_com_documento(self) -> None:
        with tempfile.TemporaryDirectory() as diretorio_temporario:
            base = Path(diretorio_temporario)
            config_dir = base / "config"
            workspace_dir = base / "workspace"
            config_dir.mkdir(parents=True, exist_ok=True)
            workspace_dir.mkdir(parents=True, exist_ok=True)

            regulamento = {
                "nome_programa": "Jornada Exportadora Autopartes - Argentina e Peru 2026",
                "versao": "1.0",
                "elegibilidade": [],
                "pontuacao": {
                    "nota_minima_classificacao": 5,
                    "criterios": [
                        {
                            "id": "website_rede_social",
                            "tipo": "presence_score",
                            "campo": "website_empresa",
                            "pontuacao": 1,
                        }
                    ],
                },
                "desempate": [],
            }
            caminho_preset = config_dir / "autopartes.json"
            caminho_preset.write_text(json.dumps(regulamento), encoding="utf-8")

            planilha = base / "inscricoes.csv"
            planilha.write_text(
                "Inscrição (Código),Nome Fantasia,CNPJ,Website\n"
                "INS-1,Empresa A,12.345.678/0001-99,https://empresa-a.com\n",
                encoding="utf-8",
            )
            documento = base / "26.01.16 - Regulamento Jornada Exportadora Argentina e Peru 2026 - Autopartes.txt"
            documento.write_text(
                "REGULAMENTO GERAL DE PARTICIPACAO\nJORNADA EXPORTADORA AUTOPARTES - ARGENTINA E PERU 2026\n",
                encoding="utf-8",
            )

            resultado = preparar_regulamento_documental(
                planilha,
                documento,
                config_dir=config_dir,
                workspace_dir=workspace_dir,
            )

            self.assertEqual(resultado.origem, "preset")
            self.assertEqual(resultado.caminho_config, caminho_preset)
            self.assertEqual(resultado.total_criterios_pontuacao, 1)

    def test_deve_gerar_config_executavel_quando_nao_ha_preset(self) -> None:
        with tempfile.TemporaryDirectory() as diretorio_temporario:
            base = Path(diretorio_temporario)
            config_dir = base / "config"
            workspace_dir = base / "workspace"
            config_dir.mkdir(parents=True, exist_ok=True)
            workspace_dir.mkdir(parents=True, exist_ok=True)

            planilha = base / "inscricoes.csv"
            planilha.write_text(
                "Inscrição (Código),Nome Fantasia,CNPJ,Status Financeiro,Website,PEIEX\n"
                "INS-1,Empresa A,12.345.678/0001-99,Adimplente,https://empresa-a.com,Sim\n",
                encoding="utf-8",
            )
            documento = base / "nova_acao.txt"
            documento.write_text(
                "O edital atribui 1 ponto para website ou rede social, 1 ponto para PEIEX "
                "e exige pontuacao minima de 1 para classificacao.",
                encoding="utf-8",
            )

            resultado = preparar_regulamento_documental(
                planilha,
                documento,
                config_dir=config_dir,
                workspace_dir=workspace_dir,
            )

            self.assertEqual(resultado.origem, "compilado")
            self.assertTrue(resultado.caminho_config.exists())

            conteudo = json.loads(resultado.caminho_config.read_text(encoding="utf-8"))
            self.assertEqual(conteudo["pontuacao"]["nota_minima_classificacao"], 1.0)
            self.assertEqual(
                [criterio["id"] for criterio in conteudo["pontuacao"]["criterios"]],
                ["website_rede_social", "peiex"],
            )


if __name__ == "__main__":
    unittest.main()
