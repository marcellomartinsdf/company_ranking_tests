from __future__ import annotations

import argparse

from services.pipeline import executar_ranqueamento


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Executa o ranqueamento de inscricoes para jornadas de exportacao."
    )
    parser.add_argument(
        "--entrada",
        required=True,
        help="Arquivo de entrada em CSV ou XLSX exportado do Dynamics.",
    )
    parser.add_argument(
        "--regulamento",
        default="config/regulamento_exemplo.json",
        help="Arquivo JSON com regras do regulamento.",
    )
    parser.add_argument(
        "--saida",
        default="saida/ranking_apex.xlsx",
        help="Arquivo XLSX de saida.",
    )
    parser.add_argument(
        "--aba",
        default=None,
        help="Nome da aba do XLSX de entrada. Sobrescreve a configuracao do regulamento.",
    )
    return parser


def main() -> None:
    parser = construir_parser()
    args = parser.parse_args()

    resumo = executar_ranqueamento(
        args.entrada,
        args.regulamento,
        args.saida,
        aba=args.aba,
    )

    print(f"Inscricoes processadas: {resumo.total_inscricoes}")
    print(f"Classificadas: {resumo.total_classificadas}")
    print(f"Com revisao pendente: {resumo.total_revisoes}")
    print(f"Arquivo gerado em: {resumo.saida_path}")


if __name__ == "__main__":
    main()
