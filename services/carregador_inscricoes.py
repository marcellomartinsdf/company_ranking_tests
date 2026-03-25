from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from models import Inscricao
from models.inscricao import normalizar_chave


def carregar_inscricoes(
    caminho: str | Path,
    *,
    sheet_name: str | None = None,
    field_map: dict[str, Any] | None = None,
) -> list[Inscricao]:
    path = Path(caminho)
    extensao = path.suffix.lower()

    if extensao == ".csv":
        return _carregar_csv(path, field_map=field_map)
    if extensao in {".xlsx", ".xlsm"}:
        return _carregar_xlsx(path, sheet_name=sheet_name, field_map=field_map)

    raise ValueError("Formato de entrada nao suportado. Use CSV ou XLSX.")


def _carregar_csv(
    path: Path,
    *,
    field_map: dict[str, Any] | None = None,
) -> list[Inscricao]:
    with path.open("r", encoding="utf-8-sig", newline="") as arquivo:
        amostra = arquivo.read(2048)
        arquivo.seek(0)
        try:
            dialect = csv.Sniffer().sniff(amostra, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel

        leitor = csv.DictReader(arquivo, dialect=dialect)
        return [
            Inscricao.from_row(_aplicar_mapeamento_campos(linha, field_map))
            for linha in leitor
            if any(linha.values())
        ]


def _carregar_xlsx(
    path: Path,
    *,
    sheet_name: str | None = None,
    field_map: dict[str, Any] | None = None,
) -> list[Inscricao]:
    workbook = load_workbook(filename=path, read_only=True, data_only=True)
    worksheet = _resolver_worksheet(workbook, sheet_name)
    linhas = worksheet.iter_rows(values_only=True)
    cabecalho = _obter_primeira_linha_preenchida(linhas)
    if cabecalho is None:
        workbook.close()
        return []

    inscricoes: list[Inscricao] = []
    for linha in linhas:
        if linha is None or not any(celula is not None and str(celula).strip() for celula in linha):
            continue
        row_dict = {
            str(cabecalho[indice] or f"coluna_{indice + 1}"): linha[indice]
            for indice in range(len(cabecalho))
        }
        inscricoes.append(Inscricao.from_row(_aplicar_mapeamento_campos(row_dict, field_map)))

    workbook.close()
    return inscricoes


def _resolver_worksheet(workbook, sheet_name: str | None):
    if not sheet_name:
        return workbook.active

    if sheet_name in workbook.sheetnames:
        return workbook[sheet_name]

    nome_desejado = normalizar_chave(sheet_name)
    for nome_aba in workbook.sheetnames:
        if normalizar_chave(nome_aba) == nome_desejado:
            return workbook[nome_aba]

    return workbook.active


def _obter_primeira_linha_preenchida(linhas) -> tuple[Any, ...] | None:
    for linha in linhas:
        if linha is not None and any(celula is not None and str(celula).strip() for celula in linha):
            return linha
    return None


def _aplicar_mapeamento_campos(
    row_dict: dict[str, Any],
    field_map: dict[str, Any] | None,
) -> dict[str, Any]:
    if not field_map:
        return row_dict

    row_mapeado = dict(row_dict)
    lookup_normalizado = {
        normalizar_chave(chave): valor
        for chave, valor in row_dict.items()
        if chave is not None
    }

    for campo_destino, aliases in field_map.items():
        aliases_lista = aliases if isinstance(aliases, list) else [aliases]
        for alias in aliases_lista:
            chave_alias = normalizar_chave(alias)
            if chave_alias not in lookup_normalizado:
                continue
            valor = lookup_normalizado[chave_alias]
            if valor is None or str(valor).strip() == "":
                continue
            row_mapeado[campo_destino] = valor
            break

    return row_mapeado
