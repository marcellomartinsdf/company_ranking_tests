from __future__ import annotations

import unittest

from models import Inscricao
from services.verificacao_automatica import (
    ConsultaCNPJOficial,
    RecursoRemoto,
    VerificacaoAutomaticaService,
)


REGULAMENTO_VERIFICACAO_TESTE = {
    "verificacoes_automaticas": {
        "usar_openai_quando_disponivel": False,
        "status_financeiro": {
            "campo": "status_financeiro",
            "valores_sem_pendencia": ["Adimplente"],
            "tokens_com_pendencia": ["inadimpl", "pendenc"],
        },
        "cnpj": {"campo": "cnpj"},
        "website_social": {
            "campo": "website_empresa",
            "campo_saida": "website_ou_rede_social_verificado",
        },
        "website_internacional": {
            "campo_link": "website_internacional_link",
            "campo_resposta": "website_internacional_resposta",
            "campo_saida": "website_internacional_verificado",
        },
        "cartao_cnpj": {
            "campos_link": ["cartao_cnpj_link"],
            "campo_saida": "cartao_cnpj_verificado",
        },
    }
}


class VerificacaoAutomaticaFake(VerificacaoAutomaticaService):
    def __init__(self, recursos: dict[str, RecursoRemoto]) -> None:
        super().__init__(REGULAMENTO_VERIFICACAO_TESTE)
        self.recursos = recursos

    def _obter_recurso(self, url: str) -> RecursoRemoto:
        if url not in self.recursos:
            return RecursoRemoto(url=url, final_url=url, erro="nao mapeado no teste")
        return self.recursos[url]


class VerificacaoAutomaticaComConsultaCNPJFake(VerificacaoAutomaticaService):
    def __init__(self, consultas: dict[str, ConsultaCNPJOficial]) -> None:
        regulamento = {
            "verificacoes_automaticas": {
                **REGULAMENTO_VERIFICACAO_TESTE["verificacoes_automaticas"],
                "cnpj_consulta_oficial": {
                    "habilitado": True,
                    "fonte": "arquivo_local",
                    "arquivo": "/tmp/falso.csv",
                    "campo_saida": "cnpj_empresa_confere_cadastro_oficial",
                },
            }
        }
        super().__init__(regulamento)
        self.consultas = consultas

    def _consultar_cnpj_fonte_oficial(
        self,
        cnpj: str,
        config: dict[str, object],
    ) -> ConsultaCNPJOficial:
        return self.consultas.get(
            cnpj,
            ConsultaCNPJOficial(cnpj=cnpj, fonte="fake", encontrado=False),
        )


class VerificacaoAutomaticaTestCase(unittest.TestCase):
    def test_deve_validar_cnpj_e_derivar_status_financeiro(self) -> None:
        service = VerificacaoAutomaticaFake({})
        inscricao = Inscricao.from_row(
            {
                "inscricao_id": "1",
                "empresa_nome": "Empresa A",
                "cnpj": "36.521.719/0001-15",
                "status_financeiro": "Adimplente",
            }
        )

        service.enriquecer_inscricao(inscricao)

        self.assertTrue(inscricao.obter_campo("cnpj_valido"))
        self.assertFalse(inscricao.obter_campo("possui_pendencia_financeira_apex"))
        self.assertIn("digitos verificadores", inscricao.obter_campo("cnpj_justificativa"))

    def test_deve_verificar_website_e_idioma_por_heuristica(self) -> None:
        url = "https://www.blgusinagem.com.br"
        recursos = {
            url: RecursoRemoto(
                url=url,
                final_url=url,
                content_type="text/html",
                html_lang="en-US",
                title="BLG Usinagem - Machined Parts for Global Buyers",
                texto=(
                    "BLG Usinagem machined parts solutions products contact export "
                    "buyers international solutions products home"
                ),
            )
        }
        service = VerificacaoAutomaticaFake(recursos)
        inscricao = Inscricao.from_row(
            {
                "inscricao_id": "2",
                "empresa_nome": "BLG Usinagem de Pecas",
                "razao_social": "BLG USINAGEM DE PECAS LTDA",
                "website_empresa": "www.blgusinagem.com.br",
                "website_internacional_resposta": "Sim",
                "website_internacional_link": "https://www.blgusinagem.com.br",
            }
        )

        service.enriquecer_inscricao(inscricao)

        self.assertTrue(inscricao.obter_campo("website_ou_rede_social_verificado"))
        self.assertTrue(inscricao.obter_campo("website_internacional_verificado"))
        self.assertFalse(inscricao.obter_campo("website_internacional_verificado_revisao_humana"))
        self.assertIn("ingles", inscricao.obter_campo("website_internacional_verificado_justificativa"))

    def test_deve_verificar_cartao_cnpj_com_texto_extraido(self) -> None:
        url = "https://docs.example.com/cartao-cnpj.pdf"
        recursos = {
            url: RecursoRemoto(
                url=url,
                final_url=url,
                content_type="text/plain",
                texto=(
                    "Comprovante de Inscricao e de Situacao Cadastral "
                    "CNPJ: 36.521.719/0001-15 "
                    "BLG USINAGEM DE PECAS LTDA"
                ),
            )
        }
        service = VerificacaoAutomaticaFake(recursos)
        inscricao = Inscricao.from_row(
            {
                "inscricao_id": "3",
                "empresa_nome": "BLG Usinagem de Pecas",
                "razao_social": "BLG USINAGEM DE PECAS LTDA",
                "cnpj": "36.521.719/0001-15",
                "cartao_cnpj_link": url,
            }
        )

        service.enriquecer_inscricao(inscricao)

        self.assertTrue(inscricao.obter_campo("cartao_cnpj_verificado"))
        self.assertTrue(inscricao.obter_campo("cartao_cnpj_cnpj_confere"))
        self.assertTrue(inscricao.obter_campo("cartao_cnpj_razao_social_confere"))

    def test_deve_confirmar_que_cnpj_confere_com_empresa_em_fonte_oficial(self) -> None:
        cnpj = "36521719000115"
        service = VerificacaoAutomaticaComConsultaCNPJFake(
            {
                cnpj: ConsultaCNPJOficial(
                    cnpj=cnpj,
                    razao_social="BLG USINAGEM DE PECAS LTDA",
                    nome_fantasia="BLG Usinagem de Pecas",
                    situacao_cadastral="ATIVA",
                    fonte="fake://cnpj",
                    encontrado=True,
                )
            }
        )
        inscricao = Inscricao.from_row(
            {
                "inscricao_id": "4",
                "empresa_nome": "BLG Usinagem de Pecas",
                "razao_social": "BLG USINAGEM DE PECAS LTDA",
                "cnpj": "36.521.719/0001-15",
            }
        )

        service.enriquecer_inscricao(inscricao)

        self.assertTrue(inscricao.obter_campo("cnpj_empresa_confere_cadastro_oficial"))
        self.assertIn(
            "cadastro oficial",
            inscricao.obter_campo("cnpj_empresa_confere_cadastro_oficial_justificativa").lower(),
        )
        self.assertEqual(
            inscricao.obter_campo("cnpj_cadastro_oficial_situacao_cadastral"),
            "ATIVA",
        )

    def test_deve_apontar_divergencia_quando_empresa_nao_confere_com_fonte_oficial(self) -> None:
        cnpj = "36521719000115"
        service = VerificacaoAutomaticaComConsultaCNPJFake(
            {
                cnpj: ConsultaCNPJOficial(
                    cnpj=cnpj,
                    razao_social="OUTRA EMPRESA LTDA",
                    nome_fantasia="OUTRA MARCA",
                    situacao_cadastral="ATIVA",
                    fonte="fake://cnpj",
                    encontrado=True,
                )
            }
        )
        inscricao = Inscricao.from_row(
            {
                "inscricao_id": "5",
                "empresa_nome": "BLG Usinagem de Pecas",
                "razao_social": "BLG USINAGEM DE PECAS LTDA",
                "cnpj": "36.521.719/0001-15",
            }
        )

        service.enriquecer_inscricao(inscricao)

        self.assertFalse(inscricao.obter_campo("cnpj_empresa_confere_cadastro_oficial"))
        self.assertIn(
            "nao corresponde",
            inscricao.obter_campo("cnpj_empresa_confere_cadastro_oficial_justificativa").lower(),
        )


if __name__ == "__main__":
    unittest.main()
