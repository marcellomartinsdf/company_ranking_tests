from __future__ import annotations

from datetime import datetime
from functools import cmp_to_key
from typing import Any

from models import ResultadoInscricao
from models.inscricao import normalizar_texto


class RankingService:
    STATUS_CLASSIFICAVEIS = {
        "classificada",
        "classificada_com_revisao_pendente",
        "aguardando_analise_de_demanda",
    }

    def __init__(self, regulamento: dict[str, Any]) -> None:
        self.regulamento = regulamento
        self.regras_desempate = regulamento.get("desempate", [])

    def classificar(self, resultados: list[ResultadoInscricao]) -> list[ResultadoInscricao]:
        classificaveis = [
            resultado
            for resultado in resultados
            if resultado.status_final in self.STATUS_CLASSIFICAVEIS
        ]
        nao_classificadas = [
            resultado
            for resultado in resultados
            if resultado.status_final not in self.STATUS_CLASSIFICAVEIS
        ]

        classificaveis_ordenadas = sorted(
            classificaveis,
            key=cmp_to_key(self._comparar_resultados),
        )
        for indice, resultado in enumerate(classificaveis_ordenadas, start=1):
            resultado.classificacao = indice

        nao_classificadas_ordenadas = sorted(
            nao_classificadas,
            key=lambda resultado: (
                0 if resultado.elegivel else 1,
                -resultado.pontuacao_total,
                normalizar_texto(resultado.inscricao.empresa_nome),
            ),
        )
        return classificaveis_ordenadas + nao_classificadas_ordenadas

    def _comparar_resultados(
        self,
        primeiro: ResultadoInscricao,
        segundo: ResultadoInscricao,
    ) -> int:
        comparacao = self._comparar_valores(
            primeiro.pontuacao_total,
            segundo.pontuacao_total,
            ordem="desc",
        )
        if comparacao != 0:
            return comparacao

        for regra in self.regras_desempate:
            valor_primeiro = self._obter_valor_desempate(primeiro, regra)
            valor_segundo = self._obter_valor_desempate(segundo, regra)
            comparacao = self._comparar_valores(
                valor_primeiro,
                valor_segundo,
                ordem=regra.get("ordem", "desc"),
            )
            if comparacao != 0:
                return comparacao

        return self._comparar_valores(
            primeiro.inscricao.empresa_nome,
            segundo.inscricao.empresa_nome,
            ordem="asc",
        )

    def _obter_valor_desempate(
        self,
        resultado: ResultadoInscricao,
        regra: dict[str, Any],
    ) -> Any:
        if regra.get("tipo") == "criterio":
            criterio = resultado.obter_resultado_criterio(regra["criterio_id"])
            return criterio.pontuacao if criterio else None
        if regra.get("tipo") == "soma_criterios":
            total = 0.0
            encontrou = False
            for criterio_id in regra.get("criterios", []):
                criterio = resultado.obter_resultado_criterio(criterio_id)
                if criterio is None:
                    continue
                encontrou = True
                total += criterio.pontuacao
            return total if encontrou else None
        if regra.get("tipo") == "campo":
            return resultado.inscricao.obter_campo(regra["campo"])
        return None

    def _comparar_valores(self, valor_a: Any, valor_b: Any, *, ordem: str) -> int:
        a = self._normalizar_para_comparacao(valor_a)
        b = self._normalizar_para_comparacao(valor_b)

        if a is None and b is None:
            return 0
        if a is None:
            return 1
        if b is None:
            return -1

        if a < b:
            return -1 if ordem == "asc" else 1
        if a > b:
            return 1 if ordem == "asc" else -1
        return 0

    def _normalizar_para_comparacao(self, valor: Any) -> Any:
        if valor is None:
            return None
        if isinstance(valor, datetime):
            return valor
        if isinstance(valor, (int, float, bool)):
            return valor
        return normalizar_texto(valor)
