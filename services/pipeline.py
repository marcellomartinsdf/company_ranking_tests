from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from models.inscricao import normalizar_chave, normalizar_texto
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
    inscricoes = _aplicar_filtros_entrada(inscricoes, origem_dados.get("filtros_entrada"))
    inscricoes = _aplicar_deduplicacao_entrada(inscricoes, origem_dados.get("deduplicacao"))
    verificador = VerificacaoAutomaticaService(regulamento)
    inscricoes = verificador.enriquecer_inscricoes(inscricoes)

    motor = MotorRegras(regulamento)
    resultados = [motor.avaliar(inscricao) for inscricao in inscricoes]

    ranking_service = RankingService(regulamento)
    ranking_ordenado = ranking_service.classificar(resultados)

    exportador = ExportadorExcel(regulamento=regulamento)
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


def _aplicar_filtros_entrada(
    inscricoes: list,
    filtros: list[dict[str, Any]] | None,
) -> list:
    if not filtros:
        return inscricoes

    inscricoes_filtradas = []
    for inscricao in inscricoes:
        incluir = True
        for filtro in filtros:
            corresponde = _filtro_corresponde(inscricao, filtro)
            modo = str(filtro.get("modo", "include")).strip().lower()
            if modo == "exclude" and corresponde:
                incluir = False
                break
            if modo != "exclude" and not corresponde:
                incluir = False
                break
        if incluir:
            inscricoes_filtradas.append(inscricao)
    return inscricoes_filtradas


def _aplicar_deduplicacao_entrada(
    inscricoes: list,
    config: dict[str, Any] | None,
) -> list:
    if not config:
        return inscricoes

    tipo = str(config.get("tipo", "")).strip().lower()
    if tipo != "cnpj_primeira_submissao":
        raise ValueError(f"Tipo de deduplicacao de entrada nao suportado: {tipo}")

    campo = str(config.get("campo", "cnpj")).strip() or "cnpj"
    campo_data = str(config.get("campo_data", "data_submissao")).strip() or "data_submissao"

    melhores_por_chave: dict[str, tuple[int, Any, Any]] = {}
    for indice, inscricao in enumerate(inscricoes):
        valor_chave = inscricao.obter_campo(campo)
        chave = normalizar_chave(str(valor_chave)) if _tem_valor(valor_chave) else ""
        if not chave:
            chave = f"__sem_chave__{indice}"

        data_referencia = inscricao.obter_campo(campo_data)
        if chave not in melhores_por_chave:
            melhores_por_chave[chave] = (indice, data_referencia, inscricao)
            continue

        indice_atual, data_atual, _ = melhores_por_chave[chave]
        if _inscricao_deve_substituir_atual(
            data_nova=data_referencia,
            data_atual=data_atual,
            indice_novo=indice,
            indice_atual=indice_atual,
        ):
            melhores_por_chave[chave] = (indice, data_referencia, inscricao)

    selecionadas = sorted(melhores_por_chave.values(), key=lambda item: item[0])
    return [inscricao for _, _, inscricao in selecionadas]


def _inscricao_deve_substituir_atual(
    *,
    data_nova: Any,
    data_atual: Any,
    indice_novo: int,
    indice_atual: int,
) -> bool:
    if data_nova is None and data_atual is None:
        return indice_novo < indice_atual
    if data_nova is None:
        return False
    if data_atual is None:
        return True
    if data_nova == data_atual:
        return indice_novo < indice_atual
    return data_nova < data_atual


def _filtro_corresponde(inscricao, filtro: dict[str, Any]) -> bool:
    tipo = str(filtro.get("tipo", "texto_em_lista")).strip().lower()
    campos = filtro.get("campos") or ([filtro.get("campo")] if filtro.get("campo") else [])
    valores = filtro.get("valores") or []
    valores_observados = [
        inscricao.obter_campo(campo)
        for campo in campos
        if campo
    ]

    if tipo == "texto_em_lista":
        valores_esperados = {normalizar_texto(valor) for valor in valores if _tem_valor(valor)}
        return any(
            normalizar_texto(valor_observado) in valores_esperados
            for valor_observado in valores_observados
            if _tem_valor(valor_observado)
        )

    if tipo == "texto_contem_algum":
        tokens = [valor for valor in valores if _tem_valor(valor)]
        return any(
            _texto_contem_normalizado(valor_observado, token)
            for valor_observado in valores_observados
            if _tem_valor(valor_observado)
            for token in tokens
        )

    raise ValueError(f"Tipo de filtro de entrada nao suportado: {tipo}")


def _tem_valor(valor: Any) -> bool:
    if valor is None:
        return False
    if isinstance(valor, str):
        return bool(valor.strip())
    return True


def _texto_contem_normalizado(valor_observado: Any, termo: Any) -> bool:
    texto = normalizar_texto(valor_observado)
    texto_chave = normalizar_chave(valor_observado)
    termo_texto = normalizar_texto(termo)
    termo_chave = normalizar_chave(termo)
    return (
        (bool(termo_texto) and termo_texto in texto)
        or (bool(termo_chave) and termo_chave in texto_chave)
    )
