from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from models.inscricao import normalizar_chave
from services.analise_regulamento import (
    detectar_criterios,
    extrair_texto_regulamento,
    inspecionar_planilha,
    sugerir_mapeamentos,
)
from services.carregador_config import carregar_regulamento


TOKENS_GENERICOS_REGULAMENTO = {
    "acao",
    "acoes",
    "apex",
    "apexbrasil",
    "brasil",
    "criterios",
    "edital",
    "empresa",
    "empresas",
    "exportacao",
    "exportadora",
    "geral",
    "jornada",
    "participacao",
    "programa",
    "regulamento",
}


@dataclass
class RegulamentoDocumentalCompilado:
    caminho_config: Path
    origem: str
    nome_programa: str
    nota_minima_classificacao: float
    total_criterios_pontuacao: int


def preparar_regulamento_documental(
    entrada_path: str | Path,
    regulamento_path: str | Path,
    *,
    config_dir: str | Path,
    workspace_dir: str | Path,
    aba: str | None = None,
) -> RegulamentoDocumentalCompilado:
    regulamento = Path(regulamento_path)
    texto = extrair_texto_regulamento(regulamento)

    preset_path = _encontrar_regulamento_preset(
        texto_regulamento=texto,
        nome_arquivo=regulamento.name,
        config_dir=config_dir,
    )
    if preset_path is not None:
        config = carregar_regulamento(preset_path)
        return RegulamentoDocumentalCompilado(
            caminho_config=preset_path,
            origem="preset",
            nome_programa=str(config.get("nome_programa") or preset_path.stem),
            nota_minima_classificacao=float(
                config.get("pontuacao", {}).get("nota_minima_classificacao", 0) or 0
            ),
            total_criterios_pontuacao=len(config.get("pontuacao", {}).get("criterios", [])),
        )

    config_compilada = compilar_regulamento_documental(
        entrada_path=entrada_path,
        regulamento_path=regulamento,
        texto_regulamento=texto,
        aba=aba,
    )
    caminho_config = Path(workspace_dir) / "regulamento_compilado.json"
    caminho_config.write_text(
        json.dumps(config_compilada, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return RegulamentoDocumentalCompilado(
        caminho_config=caminho_config,
        origem="compilado",
        nome_programa=str(config_compilada.get("nome_programa") or regulamento.stem),
        nota_minima_classificacao=float(
            config_compilada.get("pontuacao", {}).get("nota_minima_classificacao", 0) or 0
        ),
        total_criterios_pontuacao=len(config_compilada.get("pontuacao", {}).get("criterios", [])),
    )


def compilar_regulamento_documental(
    *,
    entrada_path: str | Path,
    regulamento_path: str | Path,
    texto_regulamento: str,
    aba: str | None = None,
) -> dict[str, Any]:
    inspecao = inspecionar_planilha(entrada_path, sheet_name=aba)
    criterios_detectados = detectar_criterios(texto_regulamento)
    mapeamentos = sugerir_mapeamentos(inspecao["headers"])
    field_map = {
        item["campo_destino"]: [item["header_origem"]]
        for item in mapeamentos
        if item["header_origem"]
    }
    campos_disponiveis = set(field_map)

    verificacoes_automaticas = _montar_verificacoes_automaticas(campos_disponiveis)
    elegibilidade = _montar_elegibilidade(criterios_detectados, campos_disponiveis)
    verificacoes = _montar_verificacoes(criterios_detectados, campos_disponiveis)
    criterios_pontuacao = _montar_criterios_pontuacao(criterios_detectados, campos_disponiveis)

    if not criterios_pontuacao:
        raise ValueError(
            "Nao foi possivel transformar o regulamento documental em criterios de pontuacao executaveis. "
            "Envie um regulamento JSON ou escolha a opcao de analise documental."
        )

    config: dict[str, Any] = {
        "nome_programa": _extrair_nome_programa(texto_regulamento, Path(regulamento_path).stem),
        "versao": "rascunho_documental",
        "origem_dados": {
            "sheet_name": inspecao["sheet_name"],
            "mapeamento_campos": field_map,
        },
        "elegibilidade": elegibilidade,
        "verificacoes": verificacoes,
        "pontuacao": {
            "nota_minima_classificacao": _detectar_nota_minima(texto_regulamento),
            "criterios": criterios_pontuacao,
        },
        "desempate": _montar_desempate(criterios_pontuacao, campos_disponiveis),
    }
    if verificacoes_automaticas:
        config["verificacoes_automaticas"] = verificacoes_automaticas
    return config


def _encontrar_regulamento_preset(
    *,
    texto_regulamento: str,
    nome_arquivo: str,
    config_dir: str | Path,
) -> Path | None:
    diretorio = Path(config_dir)
    tokens_nome = _tokenizar_texto(Path(nome_arquivo).stem)
    tokens_texto = _tokenizar_texto("\n".join((texto_regulamento or "").splitlines()[:20]))
    melhor_caminho: Path | None = None
    melhor_score = 0

    for caminho in sorted(diretorio.glob("*.json")):
        if caminho.name.startswith("._"):
            continue
        try:
            regulamento = carregar_regulamento(caminho)
        except Exception:
            continue

        tokens_config = _tokenizar_texto(str(regulamento.get("nome_programa") or caminho.stem))
        if not tokens_config:
            continue

        score_nome = len(tokens_nome & tokens_config)
        score_texto = len(tokens_texto & tokens_config)
        score_total = score_nome * 4 + score_texto

        if score_total > melhor_score:
            melhor_score = score_total
            melhor_caminho = caminho

    if melhor_caminho is None:
        return None
    return melhor_caminho if melhor_score >= 8 else None


def _tokenizar_texto(texto: str) -> set[str]:
    return {
        token
        for token in normalizar_chave(texto).split("_")
        if token
        and token not in TOKENS_GENERICOS_REGULAMENTO
        and (len(token) >= 4 or token.isdigit())
    }


def _extrair_nome_programa(texto_regulamento: str, fallback: str) -> str:
    linhas = [linha.strip() for linha in (texto_regulamento or "").splitlines() if linha.strip()]
    for linha in linhas:
        if len(linha) < 8:
            continue
        texto = re.sub(r"\s+", " ", linha).strip(" -")
        if "regulamento" in normalizar_chave(texto):
            continue
        return texto[:160]
    return fallback


def _detectar_nota_minima(texto_regulamento: str) -> float:
    texto = re.sub(r"\s+", " ", texto_regulamento or "", flags=re.MULTILINE)
    padroes = [
        r"pontuacao minima[^0-9]{0,24}(\d+(?:[.,]\d+)?)",
        r"nota minima[^0-9]{0,24}(\d+(?:[.,]\d+)?)",
        r"minima de classificacao[^0-9]{0,24}(\d+(?:[.,]\d+)?)",
    ]
    for padrao in padroes:
        match = re.search(padrao, normalizar_chave(texto).replace("_", " "))
        if not match:
            continue
        return float(match.group(1).replace(",", "."))
    return 0.0


def _montar_verificacoes_automaticas(campos_disponiveis: set[str]) -> dict[str, Any]:
    config: dict[str, Any] = {
        "timeout_segundos": 12,
        "max_download_bytes": 10 * 1024 * 1024,
        "usar_openai_quando_disponivel": True,
        "openai": {
            "model": "gpt-4.1-mini",
            "timeout_segundos": 25,
        },
    }

    if "status_financeiro" in campos_disponiveis:
        config["status_financeiro"] = {
            "campo": "status_financeiro",
            "valores_sem_pendencia": ["Adimplente"],
            "tokens_com_pendencia": ["inadimpl", "pendenc", "debito"],
        }
    if "cnpj" in campos_disponiveis:
        config["cnpj"] = {"campo": "cnpj"}
    if "website_empresa" in campos_disponiveis:
        config["website_social"] = {
            "campo": "website_empresa",
            "campo_saida": "website_ou_rede_social_verificado",
        }
    if {
        "website_empresa",
        "website_internacional_link",
        "website_internacional_resposta",
    } & campos_disponiveis:
        config["website_internacional"] = {
            "campo_link": "website_internacional_link",
            "campo_resposta": "website_internacional_resposta",
            "campo_saida": "website_internacional_verificado",
        }
    if {"cartao_cnpj_link", "cartao_cnpj_regional_link"} & campos_disponiveis:
        campos_link = [
            campo
            for campo in ["cartao_cnpj_link", "cartao_cnpj_regional_link"]
            if campo in campos_disponiveis
        ]
        config["cartao_cnpj"] = {
            "campos_link": campos_link,
            "campo_saida": "cartao_cnpj_verificado",
        }

    return config


def _montar_elegibilidade(
    criterios_detectados: list[dict[str, Any]],
    campos_disponiveis: set[str],
) -> list[dict[str, Any]]:
    ids = {item["criterio_id"] for item in criterios_detectados}
    criterios: list[dict[str, Any]] = []

    if "publico_alvo" in ids:
        if "classificacao_porte_maturidade" in campos_disponiveis:
            criterios.append(
                {
                    "id": "perfil_publico_alvo",
                    "nome": "Perfil de porte e maturidade aderente",
                    "tipo": "equals",
                    "campo": "classificacao_porte_maturidade",
                    "valor_esperado": "Perfil aderente",
                    "politica_campo_ausente": "review",
                    "aprovar_provisoriamente_quando_pendente": True,
                }
            )
        elif "perfil_publico_alvo_declarado" in campos_disponiveis:
            criterios.append(
                {
                    "id": "perfil_publico_alvo",
                    "nome": "Publico-alvo declarado",
                    "tipo": "equals",
                    "campo": "perfil_publico_alvo_declarado",
                    "valor_esperado": True,
                    "politica_campo_ausente": "review",
                    "aprovar_provisoriamente_quando_pendente": True,
                }
            )

    if "pendencia_financeira" in ids and "status_financeiro" in campos_disponiveis:
        criterios.append(
            {
                "id": "pendencia_financeira_apex",
                "nome": "Ausencia de pendencia financeira",
                "tipo": "equals",
                "campo": "possui_pendencia_financeira_apex",
                "valor_esperado": False,
                "politica_campo_ausente": "review",
                "aprovar_provisoriamente_quando_pendente": True,
                "campo_valor_observado": "status_financeiro",
                "campo_justificativa": "possui_pendencia_financeira_apex_justificativa",
            }
        )

    return criterios


def _montar_verificacoes(
    criterios_detectados: list[dict[str, Any]],
    campos_disponiveis: set[str],
) -> list[dict[str, Any]]:
    ids = {item["criterio_id"] for item in criterios_detectados}
    criterios: list[dict[str, Any]] = []

    if "cnpj" in ids and "cnpj" in campos_disponiveis:
        criterios.append(
            {
                "id": "cnpj_estrutural_valido",
                "nome": "CNPJ com estrutura valida",
                "tipo": "equals",
                "campo": "cnpj_valido",
                "valor_esperado": True,
                "politica_campo_ausente": "review",
                "campo_valor_observado": "cnpj_valor_observado",
                "campo_justificativa": "cnpj_justificativa",
            }
        )

    if "website_rede_social" in ids and "website_empresa" in campos_disponiveis:
        criterios.append(
            {
                "id": "website_verificado",
                "nome": "Website ou rede social verificado",
                "tipo": "equals",
                "campo": "website_ou_rede_social_verificado",
                "valor_esperado": True,
                "politica_campo_ausente": "review",
                "campo_valor_observado": "website_ou_rede_social_verificado_valor_observado",
                "campo_justificativa": "website_ou_rede_social_verificado_justificativa",
                "campo_revisao_humana": "website_ou_rede_social_verificado_revisao_humana",
            }
        )

    if "idioma_estrangeiro" in ids and {
        "website_empresa",
        "website_internacional_link",
        "website_internacional_resposta",
    } & campos_disponiveis:
        criterios.append(
            {
                "id": "website_internacional_verificado",
                "nome": "Website internacional verificado",
                "tipo": "equals",
                "campo": "website_internacional_verificado",
                "valor_esperado": True,
                "politica_campo_ausente": "review",
                "campo_valor_observado": "website_internacional_verificado_valor_observado",
                "campo_justificativa": "website_internacional_verificado_justificativa",
                "campo_revisao_humana": "website_internacional_verificado_revisao_humana",
            }
        )

    if "cnpj" in ids and {"cartao_cnpj_link", "cartao_cnpj_regional_link"} & campos_disponiveis:
        criterios.append(
            {
                "id": "cartao_cnpj_verificado",
                "nome": "Cartao CNPJ conferido",
                "tipo": "equals",
                "campo": "cartao_cnpj_verificado",
                "valor_esperado": True,
                "politica_campo_ausente": "review",
                "campo_valor_observado": "cartao_cnpj_verificado_valor_observado",
                "campo_justificativa": "cartao_cnpj_verificado_justificativa",
                "campo_revisao_humana": "cartao_cnpj_verificado_revisao_humana",
            }
        )

    return criterios


def _montar_criterios_pontuacao(
    criterios_detectados: list[dict[str, Any]],
    campos_disponiveis: set[str],
) -> list[dict[str, Any]]:
    ids = [item["criterio_id"] for item in criterios_detectados if item["categoria"] == "pontuacao"]
    criterios: list[dict[str, Any]] = []

    for criterio_id in ids:
        criterio = _montar_criterio_pontuacao(criterio_id, campos_disponiveis)
        if criterio is not None:
            criterios.append(criterio)

    return criterios


def _montar_criterio_pontuacao(
    criterio_id: str,
    campos_disponiveis: set[str],
) -> dict[str, Any] | None:
    if criterio_id == "website_rede_social" and "website_empresa" in campos_disponiveis:
        return {
            "id": "website_rede_social",
            "nome": "Website ou rede social",
            "tipo": "presence_score",
            "campo": "website_empresa",
            "pontuacao": 1,
            "pontuacao_maxima": 1,
        }

    if criterio_id == "idioma_estrangeiro" and {
        "website_empresa",
        "website_internacional_link",
        "website_internacional_resposta",
    } & campos_disponiveis:
        return {
            "id": "idioma_estrangeiro",
            "nome": "Website ou rede social em ingles e/ou espanhol",
            "tipo": "binary_score",
            "campo": "website_internacional_verificado",
            "valor_esperado": True,
            "pontuacao": 1,
            "pontuacao_maxima": 1,
            "politica_campo_ausente": "zero",
            "campo_valor_observado": "website_internacional_verificado_valor_observado",
            "campo_justificativa": "website_internacional_verificado_justificativa",
            "campo_revisao_humana": "website_internacional_verificado_revisao_humana",
            "contabilizar_sugestao_na_nota": True,
        }

    if criterio_id == "peiex" and "participa_peiex" in campos_disponiveis:
        return {
            "id": "peiex",
            "nome": "Participacao no PEIEX",
            "tipo": "binary_score",
            "campo": "participa_peiex",
            "valor_esperado": True,
            "pontuacao": 1,
            "pontuacao_maxima": 1,
        }

    if criterio_id == "sebrae" and "participa_consultoria_sebrae_exportacao" in campos_disponiveis:
        return {
            "id": "sebrae",
            "nome": "Consultoria Sebrae para exportacao",
            "tipo": "binary_score",
            "campo": "participa_consultoria_sebrae_exportacao",
            "valor_esperado": True,
            "pontuacao": 1,
            "pontuacao_maxima": 1,
        }

    if criterio_id == "ncm" and "ncm_descricao_produtos" in campos_disponiveis:
        return {
            "id": "ncm",
            "nome": "NCM e descricao do produto",
            "tipo": "ncm_score",
            "campo": "ncm_descricao_produtos",
            "pontuacao": 1,
            "pontuacao_maxima": 1,
        }

    if criterio_id == "catalogo_material":
        campo = None
        if "catalogo_digital_link" in campos_disponiveis:
            campo = "catalogo_digital_link"
        elif "foto_produto_logomarca_link" in campos_disponiveis:
            campo = "foto_produto_logomarca_link"
        if campo:
            return {
                "id": "catalogo_material",
                "nome": "Catalogo, flyer ou material promocional",
                "tipo": "presence_score",
                "campo": campo,
                "pontuacao": 1,
                "pontuacao_maxima": 1,
                "revisao_humana": True,
                "contabilizar_sugestao_na_nota": True,
            }

    if criterio_id == "certificado_origem":
        if "possui_certificado_origem" in campos_disponiveis:
            return {
                "id": "certificado_origem",
                "nome": "Certificado de origem",
                "tipo": "binary_score",
                "campo": "possui_certificado_origem",
                "valor_esperado": True,
                "pontuacao": 1,
                "pontuacao_maxima": 1,
                "campos_evidencia": ["certificado_origem_link"]
                if "certificado_origem_link" in campos_disponiveis
                else [],
            }
        if "certificado_origem_link" in campos_disponiveis:
            return {
                "id": "certificado_origem",
                "nome": "Certificado de origem",
                "tipo": "presence_score",
                "campo": "certificado_origem_link",
                "pontuacao": 1,
                "pontuacao_maxima": 1,
                "revisao_humana": True,
                "contabilizar_sugestao_na_nota": True,
            }

    if criterio_id == "certificacao_internacional":
        if "possui_certificacao_internacional" in campos_disponiveis:
            return {
                "id": "certificacao_internacional",
                "nome": "Certificacao internacional",
                "tipo": "binary_score",
                "campo": "possui_certificacao_internacional",
                "valor_esperado": True,
                "pontuacao": 1,
                "pontuacao_maxima": 1,
                "campos_evidencia": ["certificacao_internacional_link"]
                if "certificacao_internacional_link" in campos_disponiveis
                else [],
            }
        if "certificacao_internacional_link" in campos_disponiveis:
            return {
                "id": "certificacao_internacional",
                "nome": "Certificacao internacional",
                "tipo": "presence_score",
                "campo": "certificacao_internacional_link",
                "pontuacao": 1,
                "pontuacao_maxima": 1,
                "revisao_humana": True,
                "contabilizar_sugestao_na_nota": True,
            }

    if criterio_id == "diversidade_genero" and "liderada_por_mulher" in campos_disponiveis:
        return {
            "id": "diversidade_genero",
            "nome": "Lideranca feminina",
            "tipo": "binary_score",
            "campo": "liderada_por_mulher",
            "valor_esperado": True,
            "pontuacao": 1,
            "pontuacao_maxima": 1,
        }

    if criterio_id == "diversidade_racial" and "liderada_por_pessoa_negra" in campos_disponiveis:
        return {
            "id": "diversidade_racial",
            "nome": "Lideranca negra",
            "tipo": "binary_score",
            "campo": "liderada_por_pessoa_negra",
            "valor_esperado": True,
            "pontuacao": 1,
            "pontuacao_maxima": 1,
        }

    if criterio_id == "diversidade_regional" and "diversidade_regional" in campos_disponiveis:
        return {
            "id": "diversidade_regional",
            "nome": "Sede em Norte, Nordeste ou Distrito Federal",
            "tipo": "binary_score",
            "campo": "diversidade_regional",
            "valor_esperado": True,
            "pontuacao": 1,
            "pontuacao_maxima": 1,
        }

    return None


def _montar_desempate(
    criterios_pontuacao: list[dict[str, Any]],
    campos_disponiveis: set[str],
) -> list[dict[str, Any]]:
    ids = {criterio["id"] for criterio in criterios_pontuacao}
    ordem_preferencial = [
        "idioma_estrangeiro",
        "peiex",
        "sebrae",
        "certificacao_internacional",
        "diversidade_genero",
        "diversidade_racial",
        "diversidade_regional",
    ]
    desempate = [
        {"tipo": "criterio", "criterio_id": criterio_id, "ordem": "desc"}
        for criterio_id in ordem_preferencial
        if criterio_id in ids
    ]
    if "data_submissao" in campos_disponiveis:
        desempate.append({"tipo": "campo", "campo": "data_submissao", "ordem": "asc"})
    return desempate
