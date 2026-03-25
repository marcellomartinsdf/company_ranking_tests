from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import re
import unicodedata
from typing import Any, Mapping
from uuid import uuid4


BOOL_TRUE_VALUES = {"sim", "s", "true", "t", "yes", "y"}
BOOL_FALSE_VALUES = {"nao", "n", "false", "f", "no"}


def normalizar_chave(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = "".join(char for char in texto if not unicodedata.combining(char))
    texto = re.sub(r"[^a-zA-Z0-9]+", "_", texto).strip("_").lower()
    return texto


def converter_escalar(valor: Any) -> Any:
    if valor is None:
        return None

    if isinstance(valor, datetime):
        return valor

    if isinstance(valor, bool):
        return valor

    if isinstance(valor, (int, float)):
        return valor

    texto = str(valor).strip()
    if not texto:
        return None

    texto_normalizado = normalizar_texto(texto)
    if texto_normalizado in BOOL_TRUE_VALUES:
        return True
    if texto_normalizado in BOOL_FALSE_VALUES:
        return False

    if re.fullmatch(r"-?\d+", texto):
        return int(texto)
    if re.fullmatch(r"-?\d+\.\d+", texto):
        return float(texto)
    if re.fullmatch(r"-?\d+,\d+", texto):
        return float(texto.replace(",", "."))
    if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+,\d+", texto):
        return float(texto.replace(".", "").replace(",", "."))

    data_convertida = tentar_converter_data(texto)
    if data_convertida is not None:
        return data_convertida

    return texto


def normalizar_texto(valor: Any) -> str:
    if valor is None:
        return ""
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = "".join(char for char in texto if not unicodedata.combining(char))
    return texto.strip().lower()


def tentar_converter_data(valor: str) -> datetime | None:
    formatos = (
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    )
    for formato in formatos:
        try:
            return datetime.strptime(valor, formato)
        except ValueError:
            continue
    return None


def _primeiro_preenchido(dados: Mapping[str, Any], aliases: list[str]) -> Any:
    for alias in aliases:
        chave = normalizar_chave(alias)
        if chave in dados and dados[chave] not in (None, ""):
            return dados[chave]
    return None


@dataclass
class Inscricao:
    inscricao_id: str
    empresa_nome: str
    cnpj: str | None = None
    data_submissao: datetime | None = None
    campos: dict[str, Any] = field(default_factory=dict)
    dados_originais: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Inscricao":
        dados_originais = dict(row)
        dados_normalizados = {
            normalizar_chave(chave): converter_escalar(valor)
            for chave, valor in row.items()
            if chave is not None
        }

        inscricao_id = _primeiro_preenchido(
            dados_normalizados,
            ["inscricao_id", "id_inscricao", "id", "application_id"],
        )
        empresa_nome = _primeiro_preenchido(
            dados_normalizados,
            ["empresa_nome", "nome_empresa", "empresa", "razao_social"],
        )
        cnpj = _primeiro_preenchido(dados_normalizados, ["cnpj", "cnpj_empresa"])
        data_submissao = _primeiro_preenchido(
            dados_normalizados,
            ["data_submissao", "submission_date", "created_on", "data_inscricao"],
        )

        inscricao_id = str(inscricao_id) if inscricao_id is not None else str(uuid4())
        empresa_nome = (
            str(empresa_nome) if empresa_nome is not None else f"empresa_sem_nome_{inscricao_id}"
        )
        cnpj = str(cnpj) if cnpj is not None else None
        data_submissao = data_submissao if isinstance(data_submissao, datetime) else None

        dados_normalizados["inscricao_id"] = inscricao_id
        dados_normalizados["empresa_nome"] = empresa_nome
        dados_normalizados["cnpj"] = cnpj
        dados_normalizados["data_submissao"] = data_submissao

        return cls(
            inscricao_id=inscricao_id,
            empresa_nome=empresa_nome,
            cnpj=cnpj,
            data_submissao=data_submissao,
            campos=dados_normalizados,
            dados_originais=dados_originais,
        )

    def obter_campo(self, campo: str, default: Any = None) -> Any:
        return self.campos.get(normalizar_chave(campo), default)

    def definir_campo(self, campo: str, valor: Any) -> None:
        chave = normalizar_chave(campo)
        valor_convertido = converter_escalar(valor)
        self.campos[chave] = valor_convertido

        if chave == "inscricao_id" and valor_convertido is not None:
            self.inscricao_id = str(valor_convertido)
        elif chave == "empresa_nome" and valor_convertido is not None:
            self.empresa_nome = str(valor_convertido)
        elif chave == "cnpj":
            self.cnpj = str(valor_convertido) if valor_convertido is not None else None
        elif chave == "data_submissao":
            self.data_submissao = (
                valor_convertido if isinstance(valor_convertido, datetime) else None
            )

    def to_flat_dict(self) -> dict[str, Any]:
        dados = dict(self.campos)
        dados["inscricao_id"] = self.inscricao_id
        dados["empresa_nome"] = self.empresa_nome
        dados["cnpj"] = self.cnpj
        dados["data_submissao"] = self.data_submissao.isoformat(sep=" ") if self.data_submissao else None
        return dados
