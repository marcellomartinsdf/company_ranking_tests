from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.carregador_config import carregar_regulamento
from services.carregador_inscricoes import carregar_inscricoes
from services.exportador_excel import ExportadorExcel
from services.motor_regras import MotorRegras
from services.ranking_service import RankingService
from services.verificacao_automatica import VerificacaoAutomaticaService


STATUS_CLASSIFICADAS = {
    "classificada",
    "classificada_com_revisao_pendente",
    "aguardando_analise_de_demanda",
}


@dataclass
class ResumoExecucao:
    regulamento_path: str
    entrada_path: str
    saida_path: str
    total_inscricoes: int
    total_classificadas: int
    total_revisoes: int
    contagem_status: dict[str, int]


def executar_ranqueamento(
    entrada_path: str | Path,
    regulamento_path: str | Path,
    saida_path: str | Path,
    *,
    aba: str | None = None,
) -> ResumoExecucao:
    regulamento = carregar_regulamento(regulamento_path)
    origem_dados = regulamento.get("origem_dados", {})
    sheet_name = aba or origem_dados.get("sheet_name")
    try:
        inscricoes = carregar_inscricoes(
            entrada_path,
            sheet_name=sheet_name,
            field_map=origem_dados.get("mapeamento_campos"),
        )
    except Exception as exc:
        if not _erro_aba_inexistente(exc):
            raise
        inscricoes = carregar_inscricoes(
            entrada_path,
            sheet_name=None,
            field_map=origem_dados.get("mapeamento_campos"),
        )
    verificador = VerificacaoAutomaticaService(regulamento)
    inscricoes = verificador.enriquecer_inscricoes(inscricoes)

    motor = MotorRegras(regulamento)
    resultados = [motor.avaliar(inscricao) for inscricao in inscricoes]

    ranking_service = RankingService(regulamento)
    ranking_ordenado = ranking_service.classificar(resultados)

    exportador = ExportadorExcel()
    exportador.exportar(saida_path, inscricoes, ranking_ordenado)

    contagem_status = dict(Counter(resultado.status_final for resultado in ranking_ordenado))
    total_classificadas = sum(
        1 for resultado in ranking_ordenado if resultado.status_final in STATUS_CLASSIFICADAS
    )
    total_revisoes = sum(1 for resultado in ranking_ordenado if resultado.revisao_humana_pendente)

    return ResumoExecucao(
        regulamento_path=str(regulamento_path),
        entrada_path=str(entrada_path),
        saida_path=str(saida_path),
        total_inscricoes=len(inscricoes),
        total_classificadas=total_classificadas,
        total_revisoes=total_revisoes,
        contagem_status=contagem_status,
    )


def listar_regulamentos_disponiveis(config_dir: str | Path) -> list[dict[str, Any]]:
    diretorio = Path(config_dir)
    regulamentos: list[dict[str, Any]] = []

    for caminho in sorted(diretorio.glob("*.json")):
        if caminho.name.startswith("._"):
            continue
        try:
            conteudo = carregar_regulamento(caminho)
        except Exception:
            continue

        regulamentos.append(
            {
                "arquivo": caminho.name,
                "path": str(caminho),
                "nome_programa": conteudo.get("nome_programa", caminho.stem),
                "versao": conteudo.get("versao", ""),
                "sheet_name": conteudo.get("origem_dados", {}).get("sheet_name", ""),
            }
        )

    return regulamentos


def _erro_aba_inexistente(exc: Exception) -> bool:
    mensagem = str(exc).lower()
    return "worksheet" in mensagem and "does not exist" in mensagem
