from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .inscricao import Inscricao


@dataclass
class ResultadoCriterio:
    criterio_id: str
    criterio_nome: str
    categoria: str
    resultado: str
    pontuacao: float = 0.0
    pontuacao_maxima: float | None = None
    valor_observado: Any = None
    justificativa: str = ""
    revisao_humana_pendente: bool = False
    contabilizar_na_nota: bool = True
    aprovado_provisoriamente: bool = False

    def to_dict(self, inscricao: Inscricao) -> dict[str, Any]:
        return {
            "inscricao_id": inscricao.inscricao_id,
            "empresa_nome": inscricao.empresa_nome,
            "categoria": self.categoria,
            "criterio_id": self.criterio_id,
            "criterio_nome": self.criterio_nome,
            "resultado": self.resultado,
            "pontuacao": self.pontuacao,
            "pontuacao_maxima": self.pontuacao_maxima,
            "valor_observado": self.valor_observado,
            "justificativa": self.justificativa,
            "revisao_humana_pendente": self.revisao_humana_pendente,
            "contabilizar_na_nota": self.contabilizar_na_nota,
            "aprovado_provisoriamente": self.aprovado_provisoriamente,
        }


@dataclass
class ResultadoInscricao:
    inscricao: Inscricao
    resultados_criterios: list[ResultadoCriterio] = field(default_factory=list)
    elegivel: bool = False
    elegibilidade_pendente_revisao: bool = False
    pontuacao_total: float = 0.0
    nota_minima_atendida: bool = False
    demanda_atendida: bool | None = None
    demanda_pendente_revisao: bool = False
    status_final: str = "nao_processada"
    motivo_status_final: str = ""
    classificacao: int | None = None

    @property
    def revisao_humana_pendente(self) -> bool:
        return any(resultado.revisao_humana_pendente for resultado in self.resultados_criterios)

    def obter_resultado_criterio(self, criterio_id: str) -> ResultadoCriterio | None:
        for resultado in self.resultados_criterios:
            if resultado.criterio_id == criterio_id:
                return resultado
        return None

    def to_ranking_dict(self) -> dict[str, Any]:
        return {
            "classificacao": self.classificacao,
            "status_final": self.status_final,
            "motivo_status_final": self.motivo_status_final,
            "elegivel": self.elegivel,
            "elegibilidade_pendente_revisao": self.elegibilidade_pendente_revisao,
            "nota_minima_atendida": self.nota_minima_atendida,
            "demanda_atendida": self.demanda_atendida,
            "demanda_pendente_revisao": self.demanda_pendente_revisao,
            "pontuacao_total": self.pontuacao_total,
            "revisao_humana_pendente": self.revisao_humana_pendente,
            "inscricao_id": self.inscricao.inscricao_id,
            "empresa_nome": self.inscricao.empresa_nome,
            "cnpj": self.inscricao.cnpj,
            "data_submissao": (
                self.inscricao.data_submissao.isoformat(sep=" ")
                if self.inscricao.data_submissao
                else None
            ),
        }
