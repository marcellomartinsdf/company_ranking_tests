from __future__ import annotations

import re
from typing import Any

from models import Inscricao, ResultadoCriterio, ResultadoInscricao
from models.inscricao import normalizar_texto


class MotorRegras:
    def __init__(self, regulamento: dict[str, Any]) -> None:
        self.regulamento = regulamento
        self.nota_minima = (
            float(regulamento.get("pontuacao", {}).get("nota_minima_classificacao", 0) or 0)
        )

    def avaliar(self, inscricao: Inscricao) -> ResultadoInscricao:
        resultados: list[ResultadoCriterio] = []

        elegivel = True
        elegibilidade_pendente_revisao = False
        for criterio in self.regulamento.get("elegibilidade", []):
            resultado = self._avaliar_criterio(inscricao, criterio, categoria="elegibilidade")
            resultados.append(resultado)
            if resultado.resultado == "reprovado":
                elegivel = False
            elif resultado.resultado == "pendente_revisao":
                elegibilidade_pendente_revisao = True
                if not resultado.aprovado_provisoriamente:
                    elegivel = False

        for criterio in self.regulamento.get("verificacoes", []):
            resultados.append(self._avaliar_criterio(inscricao, criterio, categoria="verificacao"))

        pontuacao_total = 0.0
        for criterio in self.regulamento.get("pontuacao", {}).get("criterios", []):
            resultado = self._avaliar_criterio(inscricao, criterio, categoria="pontuacao")
            resultados.append(resultado)
            if resultado.contabilizar_na_nota:
                pontuacao_total += resultado.pontuacao

        nota_minima_atendida = elegivel and pontuacao_total >= self.nota_minima
        demanda_atendida: bool | None = None
        demanda_pendente_revisao = False

        if nota_minima_atendida:
            criterios_demanda = self.regulamento.get("analise_demanda", [])
            if criterios_demanda:
                demanda_atendida = True
                for criterio in criterios_demanda:
                    resultado = self._avaliar_criterio(
                        inscricao,
                        criterio,
                        categoria="analise_demanda",
                    )
                    resultados.append(resultado)
                    if resultado.resultado == "reprovado":
                        demanda_atendida = False
                    elif resultado.resultado == "pendente_revisao":
                        demanda_pendente_revisao = True
                        if demanda_atendida is not False:
                            demanda_atendida = None
                        if not resultado.aprovado_provisoriamente:
                            demanda_atendida = False
            else:
                demanda_atendida = True

        status_final, motivo = self._definir_status_final(
            elegivel=elegivel,
            nota_minima_atendida=nota_minima_atendida,
            demanda_atendida=demanda_atendida,
            demanda_pendente_revisao=demanda_pendente_revisao,
            resultados=resultados,
        )

        return ResultadoInscricao(
            inscricao=inscricao,
            resultados_criterios=resultados,
            elegivel=elegivel,
            elegibilidade_pendente_revisao=elegibilidade_pendente_revisao,
            pontuacao_total=round(pontuacao_total, 2),
            nota_minima_atendida=nota_minima_atendida,
            demanda_atendida=demanda_atendida,
            demanda_pendente_revisao=demanda_pendente_revisao,
            status_final=status_final,
            motivo_status_final=motivo,
        )

    def _definir_status_final(
        self,
        *,
        elegivel: bool,
        nota_minima_atendida: bool,
        demanda_atendida: bool | None,
        demanda_pendente_revisao: bool,
        resultados: list[ResultadoCriterio],
    ) -> tuple[str, str]:
        if not elegivel:
            return "eliminada", "Nao atendeu aos criterios eliminatorios."
        if not nota_minima_atendida:
            return (
                "abaixo_do_corte",
                f"Pontuacao total abaixo da nota minima de classificacao ({self.nota_minima}).",
            )
        if demanda_atendida is False:
            return (
                "nao_selecionada_por_demanda",
                "Nao foram identificados compradores compativeis na analise de demanda do mercado-alvo.",
            )
        if demanda_pendente_revisao:
            return (
                "aguardando_analise_de_demanda",
                "Aguardando conclusao da analise de demanda e dos compradores do mercado-alvo.",
            )
        if any(resultado.revisao_humana_pendente for resultado in resultados):
            return (
                "classificada_com_revisao_pendente",
                "Classificada provisoriamente com ao menos uma sugestao pendente de revisao humana.",
            )
        return "classificada", "Atendeu aos criterios de elegibilidade, corte minimo e desempate."

    def _avaliar_criterio(
        self,
        inscricao: Inscricao,
        criterio: dict[str, Any],
        *,
        categoria: str,
    ) -> ResultadoCriterio:
        if categoria == "pontuacao":
            resultado_override = self._avaliar_score_override(inscricao, criterio)
            if resultado_override is not None:
                return self._aplicar_metadados_dinamicos(inscricao, criterio, resultado_override)

        campo = criterio.get("campo")
        valor_observado = inscricao.obter_campo(campo) if campo else None
        politica_ausencia = criterio.get(
            "politica_campo_ausente",
            "fail" if categoria == "elegibilidade" else "zero",
        )

        if valor_observado is None:
            resultado = self._resultado_campo_ausente(
                inscricao=inscricao,
                criterio=criterio,
                categoria=categoria,
                politica_ausencia=politica_ausencia,
            )
            return self._aplicar_metadados_dinamicos(inscricao, criterio, resultado)

        tipo = criterio.get("tipo")
        if tipo == "equals":
            resultado = self._avaliar_equals(criterio, categoria, valor_observado)
            return self._aplicar_metadados_dinamicos(inscricao, criterio, resultado)
        if tipo == "in":
            resultado = self._avaliar_in(criterio, categoria, valor_observado)
            return self._aplicar_metadados_dinamicos(inscricao, criterio, resultado)
        if tipo == "presence_score":
            resultado = self._avaliar_presence_score(criterio, categoria, valor_observado)
            return self._aplicar_metadados_dinamicos(inscricao, criterio, resultado)
        if tipo == "binary_score":
            resultado = self._avaliar_binary_score(inscricao, criterio, categoria, valor_observado)
            return self._aplicar_metadados_dinamicos(inscricao, criterio, resultado)
        if tipo == "ncm_score":
            resultado = self._avaliar_ncm_score(criterio, categoria, valor_observado)
            return self._aplicar_metadados_dinamicos(inscricao, criterio, resultado)
        if tipo == "range_score":
            resultado = self._avaliar_range_score(criterio, categoria, valor_observado)
            return self._aplicar_metadados_dinamicos(inscricao, criterio, resultado)
        if tipo == "value_map":
            resultado = self._avaliar_value_map(criterio, categoria, valor_observado)
            return self._aplicar_metadados_dinamicos(inscricao, criterio, resultado)
        if tipo == "gte":
            resultado = self._avaliar_gte(criterio, categoria, valor_observado)
            return self._aplicar_metadados_dinamicos(inscricao, criterio, resultado)
        if tipo == "lte":
            resultado = self._avaliar_lte(criterio, categoria, valor_observado)
            return self._aplicar_metadados_dinamicos(inscricao, criterio, resultado)

        raise ValueError(f"Tipo de criterio nao suportado: {tipo}")

    def _resultado_campo_ausente(
        self,
        *,
        inscricao: Inscricao,
        criterio: dict[str, Any],
        categoria: str,
        politica_ausencia: str,
    ) -> ResultadoCriterio:
        nome = criterio.get("nome", criterio["id"])
        mensagem = f"Campo '{criterio.get('campo')}' ausente na inscricao."
        pontuacao_maxima = self._pontuacao_maxima(criterio)
        aprovado_provisoriamente = bool(
            criterio.get("aprovar_provisoriamente_quando_pendente", False)
        )

        if politica_ausencia == "review":
            return ResultadoCriterio(
                criterio_id=criterio["id"],
                criterio_nome=nome,
                categoria=categoria,
                resultado="pendente_revisao",
                pontuacao=0.0,
                pontuacao_maxima=pontuacao_maxima,
                valor_observado=inscricao.obter_campo(criterio.get("campo")),
                justificativa=mensagem + " Encaminhado para revisao humana.",
                revisao_humana_pendente=True,
                contabilizar_na_nota=bool(criterio.get("contabilizar_sugestao_na_nota", False)),
                aprovado_provisoriamente=aprovado_provisoriamente,
            )

        if categoria == "elegibilidade" or politica_ausencia == "fail":
            return ResultadoCriterio(
                criterio_id=criterio["id"],
                criterio_nome=nome,
                categoria=categoria,
                resultado="reprovado",
                pontuacao=0.0,
                pontuacao_maxima=pontuacao_maxima,
                valor_observado=None,
                justificativa=mensagem,
                revisao_humana_pendente=False,
                contabilizar_na_nota=False,
            )

        return ResultadoCriterio(
            criterio_id=criterio["id"],
            criterio_nome=nome,
            categoria=categoria,
            resultado="pontuado",
            pontuacao=0.0,
            pontuacao_maxima=pontuacao_maxima,
            valor_observado=None,
            justificativa=mensagem + " Pontuacao atribuida como zero conforme configuracao.",
            revisao_humana_pendente=False,
            contabilizar_na_nota=True,
        )

    def _avaliar_equals(
        self,
        criterio: dict[str, Any],
        categoria: str,
        valor_observado: Any,
    ) -> ResultadoCriterio:
        esperado = criterio.get("valor_esperado")
        aprovado = self._comparar_normalizado(valor_observado, esperado)
        resultado = "aprovado" if aprovado else "reprovado"
        justificativa = (
            criterio.get("mensagem_aprovado")
            if aprovado
            else criterio.get("mensagem_reprovado")
        ) or f"Valor observado '{valor_observado}' comparado com '{esperado}'."

        return ResultadoCriterio(
            criterio_id=criterio["id"],
            criterio_nome=criterio.get("nome", criterio["id"]),
            categoria=categoria,
            resultado=resultado,
            pontuacao=0.0,
            pontuacao_maxima=self._pontuacao_maxima(criterio),
            valor_observado=valor_observado,
            justificativa=justificativa,
            revisao_humana_pendente=False,
            contabilizar_na_nota=False,
        )

    def _avaliar_presence_score(
        self,
        criterio: dict[str, Any],
        categoria: str,
        valor_observado: Any,
    ) -> ResultadoCriterio:
        texto = "" if valor_observado is None else str(valor_observado).strip()
        atende = bool(texto)

        min_length = criterio.get("min_length")
        if atende and min_length is not None:
            atende = len(texto) >= int(min_length)

        regex = criterio.get("regex")
        if atende and regex:
            atende = re.search(regex, texto) is not None

        pontuacao = float(criterio.get("pontuacao", 1 if atende else 0)) if atende else 0.0
        revisao_humana = atende and bool(criterio.get("revisao_humana", False))

        if atende:
            justificativa = criterio.get(
                "mensagem_aprovado",
                f"Campo '{criterio.get('campo')}' preenchido com evidencia suficiente.",
            )
        else:
            justificativa = criterio.get(
                "mensagem_reprovado",
                f"Campo '{criterio.get('campo')}' ausente ou insuficiente para pontuacao.",
            )

        if revisao_humana:
            justificativa = (
                f"{justificativa} "
                f"{criterio.get('mensagem_sugestao', 'Sugestao automatica pendente de revisao humana.')}"
            ).strip()

        return ResultadoCriterio(
            criterio_id=criterio["id"],
            criterio_nome=criterio.get("nome", criterio["id"]),
            categoria=categoria,
            resultado=self._resultado_score(atende, revisao_humana),
            pontuacao=pontuacao,
            pontuacao_maxima=self._pontuacao_maxima(criterio),
            valor_observado=valor_observado,
            justificativa=justificativa,
            revisao_humana_pendente=revisao_humana,
            contabilizar_na_nota=not revisao_humana
            or bool(criterio.get("contabilizar_sugestao_na_nota", True)),
        )

    def _avaliar_binary_score(
        self,
        inscricao: Inscricao,
        criterio: dict[str, Any],
        categoria: str,
        valor_observado: Any,
    ) -> ResultadoCriterio:
        resposta_positiva = self._comparar_normalizado(
            valor_observado,
            criterio.get("valor_esperado", True),
        )
        evidencia_campos = criterio.get("campos_evidencia", [])
        evidencia_ok = all(self._tem_valor(inscricao.obter_campo(campo)) for campo in evidencia_campos)

        atende = resposta_positiva and (not evidencia_campos or evidencia_ok)
        pontuacao = float(criterio.get("pontuacao", 1 if atende else 0)) if atende else 0.0
        revisao_humana = atende and bool(criterio.get("revisao_humana", False))

        if atende:
            justificativa = criterio.get(
                "mensagem_aprovado",
                f"Declaracao positiva para '{criterio.get('campo')}' com evidencia preenchida.",
            )
        elif resposta_positiva and evidencia_campos and not evidencia_ok:
            justificativa = criterio.get(
                "mensagem_reprovado",
                "Declaracao positiva sem evidencia minima exigida para validar a pontuacao.",
            )
        else:
            justificativa = criterio.get(
                "mensagem_reprovado",
                f"Declaracao nao atende ao criterio '{criterio.get('campo')}'.",
            )

        if revisao_humana:
            justificativa = (
                f"{justificativa} "
                f"{criterio.get('mensagem_sugestao', 'Sugestao automatica pendente de revisao humana.')}"
            ).strip()

        return ResultadoCriterio(
            criterio_id=criterio["id"],
            criterio_nome=criterio.get("nome", criterio["id"]),
            categoria=categoria,
            resultado=self._resultado_score(atende, revisao_humana),
            pontuacao=pontuacao,
            pontuacao_maxima=self._pontuacao_maxima(criterio),
            valor_observado=valor_observado,
            justificativa=justificativa,
            revisao_humana_pendente=revisao_humana,
            contabilizar_na_nota=not revisao_humana
            or bool(criterio.get("contabilizar_sugestao_na_nota", True)),
        )

    def _avaliar_ncm_score(
        self,
        criterio: dict[str, Any],
        categoria: str,
        valor_observado: Any,
    ) -> ResultadoCriterio:
        texto = "" if valor_observado is None else str(valor_observado)
        texto_normalizado = normalizar_texto(texto)
        possui_codigo = re.search(r"(?:\d{8}|\d{4}[.\-]?\d{2}[.\-]?\d{2})", texto) is not None
        possui_descricao = re.search(r"[a-z]", texto_normalizado) is not None
        atende = possui_codigo and possui_descricao
        pontuacao = float(criterio.get("pontuacao", 1 if atende else 0)) if atende else 0.0

        justificativa = criterio.get(
            "mensagem_aprovado" if atende else "mensagem_reprovado",
            (
                "Campo contem codigo NCM e descricao do produto."
                if atende
                else "Campo nao apresenta NCM com descricao suficiente."
            ),
        )

        return ResultadoCriterio(
            criterio_id=criterio["id"],
            criterio_nome=criterio.get("nome", criterio["id"]),
            categoria=categoria,
            resultado=self._resultado_score(atende, False),
            pontuacao=pontuacao,
            pontuacao_maxima=self._pontuacao_maxima(criterio),
            valor_observado=valor_observado,
            justificativa=justificativa,
            revisao_humana_pendente=False,
            contabilizar_na_nota=True,
        )

    def _avaliar_in(
        self,
        criterio: dict[str, Any],
        categoria: str,
        valor_observado: Any,
    ) -> ResultadoCriterio:
        valores_aceitos = criterio.get("valores_aceitos", [])
        aprovado = any(
            self._comparar_normalizado(valor_observado, valor_aceito)
            for valor_aceito in valores_aceitos
        )
        resultado = "aprovado" if aprovado else "reprovado"
        justificativa = (
            criterio.get("mensagem_aprovado")
            if aprovado
            else criterio.get("mensagem_reprovado")
        ) or f"Valor observado '{valor_observado}' comparado com lista de valores aceitos."

        return ResultadoCriterio(
            criterio_id=criterio["id"],
            criterio_nome=criterio.get("nome", criterio["id"]),
            categoria=categoria,
            resultado=resultado,
            pontuacao=0.0,
            pontuacao_maxima=self._pontuacao_maxima(criterio),
            valor_observado=valor_observado,
            justificativa=justificativa,
            revisao_humana_pendente=False,
            contabilizar_na_nota=False,
        )

    def _avaliar_gte(
        self,
        criterio: dict[str, Any],
        categoria: str,
        valor_observado: Any,
    ) -> ResultadoCriterio:
        limite = float(criterio["valor_minimo"])
        valor = float(valor_observado)
        aprovado = valor >= limite
        resultado = "aprovado" if aprovado else "reprovado"
        justificativa = f"Valor observado {valor} comparado ao minimo {limite}."

        return ResultadoCriterio(
            criterio_id=criterio["id"],
            criterio_nome=criterio.get("nome", criterio["id"]),
            categoria=categoria,
            resultado=resultado,
            pontuacao=0.0,
            pontuacao_maxima=self._pontuacao_maxima(criterio),
            valor_observado=valor_observado,
            justificativa=justificativa,
            revisao_humana_pendente=False,
            contabilizar_na_nota=False,
        )

    def _avaliar_lte(
        self,
        criterio: dict[str, Any],
        categoria: str,
        valor_observado: Any,
    ) -> ResultadoCriterio:
        limite = float(criterio["valor_maximo"])
        valor = float(valor_observado)
        aprovado = valor <= limite
        resultado = "aprovado" if aprovado else "reprovado"
        justificativa = f"Valor observado {valor} comparado ao maximo {limite}."

        return ResultadoCriterio(
            criterio_id=criterio["id"],
            criterio_nome=criterio.get("nome", criterio["id"]),
            categoria=categoria,
            resultado=resultado,
            pontuacao=0.0,
            pontuacao_maxima=self._pontuacao_maxima(criterio),
            valor_observado=valor_observado,
            justificativa=justificativa,
            revisao_humana_pendente=False,
            contabilizar_na_nota=False,
        )

    def _avaliar_range_score(
        self,
        criterio: dict[str, Any],
        categoria: str,
        valor_observado: Any,
    ) -> ResultadoCriterio:
        valor = float(valor_observado)
        faixa_escolhida = None
        for faixa in criterio.get("faixas", []):
            if self._valor_na_faixa(valor, faixa):
                faixa_escolhida = faixa
                break

        if faixa_escolhida is None:
            pontuacao = float(criterio.get("pontuacao_padrao", 0))
            justificativa = (
                f"Nenhuma faixa configurada correspondeu ao valor {valor}. "
                f"Pontuacao padrao {pontuacao} aplicada."
            )
        else:
            pontuacao = float(faixa_escolhida.get("score", 0))
            justificativa = faixa_escolhida.get(
                "justificativa",
                f"Valor {valor} enquadrado em faixa com pontuacao {pontuacao}.",
            )

        revisao_humana = bool(criterio.get("revisao_humana", False))
        if revisao_humana:
            mensagem_sugestao = criterio.get(
                "mensagem_sugestao",
                "Sugestao automatica pendente de revisao humana.",
            )
            justificativa = f"{justificativa} {mensagem_sugestao}".strip()

        return ResultadoCriterio(
            criterio_id=criterio["id"],
            criterio_nome=criterio.get("nome", criterio["id"]),
            categoria=categoria,
            resultado="pontuado" if not revisao_humana else "sugerido",
            pontuacao=pontuacao,
            pontuacao_maxima=self._pontuacao_maxima(criterio),
            valor_observado=valor_observado,
            justificativa=justificativa,
            revisao_humana_pendente=revisao_humana,
            contabilizar_na_nota=not revisao_humana
            or bool(criterio.get("contabilizar_sugestao_na_nota", True)),
        )

    def _avaliar_value_map(
        self,
        criterio: dict[str, Any],
        categoria: str,
        valor_observado: Any,
    ) -> ResultadoCriterio:
        mapa = criterio.get("mapa_valores", {})
        chave_valor = normalizar_texto(valor_observado)
        pontuacao = float(mapa.get(chave_valor, criterio.get("pontuacao_padrao", 0)))
        justificativa = f"Valor '{valor_observado}' mapeado para {pontuacao} ponto(s)."

        revisao_humana = bool(criterio.get("revisao_humana", False))
        if revisao_humana:
            mensagem_sugestao = criterio.get(
                "mensagem_sugestao",
                "Sugestao automatica pendente de revisao humana.",
            )
            justificativa = f"{justificativa} {mensagem_sugestao}".strip()

        return ResultadoCriterio(
            criterio_id=criterio["id"],
            criterio_nome=criterio.get("nome", criterio["id"]),
            categoria=categoria,
            resultado="pontuado" if not revisao_humana else "sugerido",
            pontuacao=pontuacao,
            pontuacao_maxima=self._pontuacao_maxima(criterio),
            valor_observado=valor_observado,
            justificativa=justificativa,
            revisao_humana_pendente=revisao_humana,
            contabilizar_na_nota=not revisao_humana
            or bool(criterio.get("contabilizar_sugestao_na_nota", True)),
        )

    def _avaliar_score_override(
        self,
        inscricao: Inscricao,
        criterio: dict[str, Any],
    ) -> ResultadoCriterio | None:
        campo_override = criterio.get("campo_score_override")
        if not campo_override:
            return None

        valor_override = inscricao.obter_campo(campo_override)
        if valor_override is None:
            return None

        try:
            pontuacao = 1.0 if isinstance(valor_override, bool) and valor_override else float(valor_override)
        except (TypeError, ValueError):
            return None

        valor_observado = inscricao.obter_campo(criterio.get("campo"))
        justificativa = criterio.get(
            "mensagem_override",
            f"Pontuacao importada do campo '{campo_override}' da planilha atual.",
        )

        return ResultadoCriterio(
            criterio_id=criterio["id"],
            criterio_nome=criterio.get("nome", criterio["id"]),
            categoria="pontuacao",
            resultado=self._resultado_score(pontuacao > 0, False),
            pontuacao=pontuacao,
            pontuacao_maxima=self._pontuacao_maxima(criterio),
            valor_observado=valor_observado,
            justificativa=justificativa,
            revisao_humana_pendente=False,
            contabilizar_na_nota=True,
        )

    def _pontuacao_maxima(self, criterio: dict[str, Any]) -> float | None:
        if "pontuacao_maxima" in criterio:
            return float(criterio["pontuacao_maxima"])

        if criterio.get("tipo") in {"presence_score", "binary_score", "ncm_score"}:
            return float(criterio.get("pontuacao", 1))

        if criterio.get("tipo") == "value_map":
            valores = criterio.get("mapa_valores", {}).values()
            return float(max(valores)) if valores else 0.0

        if criterio.get("tipo") == "range_score":
            pontuacoes = [float(faixa.get("score", 0)) for faixa in criterio.get("faixas", [])]
            return float(max(pontuacoes)) if pontuacoes else 0.0

        return None

    def _valor_na_faixa(self, valor: float, faixa: dict[str, Any]) -> bool:
        if "min" in faixa and valor < float(faixa["min"]):
            return False
        if "min_exclusive" in faixa and valor <= float(faixa["min_exclusive"]):
            return False
        if "max" in faixa and valor > float(faixa["max"]):
            return False
        if "max_exclusive" in faixa and valor >= float(faixa["max_exclusive"]):
            return False
        return True

    def _comparar_normalizado(self, valor_a: Any, valor_b: Any) -> bool:
        if isinstance(valor_a, bool) or isinstance(valor_b, bool):
            return bool(valor_a) == bool(valor_b)
        return normalizar_texto(valor_a) == normalizar_texto(valor_b)

    def _resultado_score(self, atende: bool, revisao_humana: bool) -> str:
        if not atende:
            return "nao_pontuado"
        if revisao_humana:
            return "sugerido"
        return "pontuado"

    def _aplicar_metadados_dinamicos(
        self,
        inscricao: Inscricao,
        criterio: dict[str, Any],
        resultado: ResultadoCriterio,
    ) -> ResultadoCriterio:
        campo_valor_observado = criterio.get("campo_valor_observado")
        if campo_valor_observado:
            valor_observado = inscricao.obter_campo(campo_valor_observado)
            if valor_observado is not None:
                resultado.valor_observado = valor_observado

        campo_justificativa = criterio.get("campo_justificativa")
        if campo_justificativa:
            justificativa = inscricao.obter_campo(campo_justificativa)
            if self._tem_valor(justificativa):
                resultado.justificativa = str(justificativa)

        campo_revisao_humana = criterio.get("campo_revisao_humana")
        if campo_revisao_humana:
            revisao_humana = inscricao.obter_campo(campo_revisao_humana)
            if revisao_humana is not None:
                resultado.revisao_humana_pendente = bool(revisao_humana)
                if resultado.revisao_humana_pendente and resultado.resultado == "pontuado":
                    resultado.resultado = "sugerido"

        if "contabilizar_na_nota" in criterio:
            resultado.contabilizar_na_nota = bool(criterio.get("contabilizar_na_nota"))
        elif resultado.revisao_humana_pendente and "contabilizar_sugestao_na_nota" in criterio:
            resultado.contabilizar_na_nota = bool(criterio.get("contabilizar_sugestao_na_nota"))

        return resultado

    def _tem_valor(self, valor: Any) -> bool:
        if valor is None:
            return False
        if isinstance(valor, str):
            return bool(valor.strip())
        return True
