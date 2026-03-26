from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from flask import Flask, flash, redirect, render_template, request, send_file, url_for
from io import BytesIO
from werkzeug.utils import secure_filename

from services.job_storage import create_job_storage
from services.pipeline import executar_ranqueamento, listar_regulamentos_disponiveis


APEXBRASIL_SITE_URL = "https://apexbrasil.com.br/"
APEXBRASIL_LOGO_URL = (
    "https://apexbrasil.com.br/content/experience-fragments/apexbrasil/br/pt/site/footer/"
    "master/_jcr_content/root/container_92666072/image.coreimg.png/1707507437950/default.png"
)


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("RANQUEAMENTO_SECRET_KEY", "ranqueamento-dev")
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
    app.config["CONFIG_DIR"] = str(Path(app.root_path) / "config")
    app.config["STORAGE_DIR"] = os.environ.get(
        "STORAGE_DIR",
        str(Path(tempfile.gettempdir()) / "ranqueamento_apex" / "jobs"),
    )
    app.config["JOB_STORAGE_BACKEND"] = os.environ.get("JOB_STORAGE_BACKEND", "local")
    app.config["AZURE_STORAGE_ACCOUNT_URL"] = os.environ.get("AZURE_STORAGE_ACCOUNT_URL")
    app.config["AZURE_STORAGE_CONNECTION_STRING"] = os.environ.get(
        "AZURE_STORAGE_CONNECTION_STRING"
    )
    app.config["AZURE_STORAGE_CONTAINER"] = os.environ.get(
        "AZURE_STORAGE_CONTAINER",
        "ranqueamento-jobs",
    )
    app.config["AZURE_STORAGE_BLOB_PREFIX"] = os.environ.get(
        "AZURE_STORAGE_BLOB_PREFIX",
        "jobs",
    )

    @app.get("/")
    def index():
        regulamentos = listar_regulamentos_disponiveis(app.config["CONFIG_DIR"])
        regulamento_aplicado = _obter_regulamento_padrao(regulamentos)
        return render_template(
            "index.html",
            regulamentos=regulamentos,
            default_regulamento=_default_regulamento(regulamentos),
            regulamento_aplicado=regulamento_aplicado,
            storage_backend=app.config["JOB_STORAGE_BACKEND"],
            apex_site_url=APEXBRASIL_SITE_URL,
            apex_logo_url=APEXBRASIL_LOGO_URL,
        )

    @app.post("/processar")
    def processar():
        planilha = request.files.get("planilha")
        regulamento_preset = request.form.get("regulamento_preset", "").strip()
        aba = request.form.get("aba", "").strip() or None
        nome_acao = request.form.get("nome_acao", "").strip()

        if planilha is None or not planilha.filename:
            flash("Selecione uma planilha de inscricoes em CSV ou XLSX.", "error")
            return redirect(url_for("index"))

        regulamentos = listar_regulamentos_disponiveis(app.config["CONFIG_DIR"])
        regulamento_aplicado = _obter_regulamento_padrao(regulamentos)
        if not regulamento_aplicado:
            flash(
                "Nenhum regulamento padrao foi encontrado na configuracao do sistema.",
                "error",
            )
            return redirect(url_for("index"))

        try:
            job_id = uuid4().hex
            storage = _get_job_storage(app)
            job_dir = storage.create_job_workspace(job_id)

            planilha_path = job_dir / _nome_seguro(planilha.filename, fallback="inscricoes.xlsx")
            planilha.save(planilha_path)

            regulamento_selecionado = _obter_regulamento_selecionado(
                regulamentos,
                regulamento_preset=regulamento_preset,
            )
            regulamento_base_path = _resolver_regulamento_preset(
                app.config["CONFIG_DIR"],
                regulamento_selecionado["arquivo"],
            )
            regulamento_label = regulamento_selecionado["nome_programa"]
            origem_regulamento = "preset"

            regulamento_path = _preparar_regulamento_execucao_web(
                regulamento_base_path,
                job_dir=job_dir,
            )
            modo = "ranqueamento"

            nome_saida = _nome_saida(
                nome_acao=nome_acao,
                planilha_filename=planilha.filename,
                modo="ranqueamento",
            )
            saida_path = job_dir / nome_saida

            resumo = executar_ranqueamento(
                planilha_path,
                regulamento_path,
                saida_path,
                aba=aba,
            )
            storage.persist_job(job_id, job_dir, nome_saida)
        except Exception as exc:
            app.logger.exception("Falha no processamento do ranqueamento")
            flash(_mensagem_falha_processamento(exc, aba=aba), "error")
            return redirect(url_for("index"))

        return render_template(
            "resultado.html",
            job_id=job_id,
            resumo=resumo,
            regulamento_label=regulamento_label,
            origem_regulamento=origem_regulamento,
            aba=aba,
            modo=modo,
            apex_site_url=APEXBRASIL_SITE_URL,
            apex_logo_url=APEXBRASIL_LOGO_URL,
        )

    @app.get("/download/<job_id>")
    def download(job_id: str):
        storage = _get_job_storage(app)
        try:
            resultado = storage.read_result(job_id)
        except Exception:
            flash("Arquivo de resultado nao encontrado.", "error")
            return redirect(url_for("index"))

        return send_file(
            BytesIO(resultado.conteudo),
            as_attachment=True,
            download_name=resultado.nome_arquivo,
            mimetype=resultado.mime_type,
        )

    @app.get("/health")
    def health():
        return {"status": "ok", "storage_backend": app.config["JOB_STORAGE_BACKEND"]}

    return app


def _default_regulamento(regulamentos: list[dict[str, str]]) -> str:
    for regulamento in regulamentos:
        if "autopartes" in regulamento["arquivo"]:
            return regulamento["arquivo"]
    return regulamentos[0]["arquivo"] if regulamentos else ""


def _obter_regulamento_padrao(regulamentos: list[dict[str, str]]) -> dict[str, str] | None:
    arquivo_padrao = _default_regulamento(regulamentos)
    return _obter_regulamento_por_arquivo(regulamentos, arquivo_padrao)


def _obter_regulamento_por_arquivo(
    regulamentos: list[dict[str, str]],
    arquivo: str | None,
) -> dict[str, str] | None:
    for regulamento in regulamentos:
        if regulamento["arquivo"] == arquivo:
            return regulamento
    return None


def _obter_regulamento_selecionado(
    regulamentos: list[dict[str, str]],
    *,
    regulamento_preset: str | None,
) -> dict[str, str]:
    arquivo = (regulamento_preset or "").strip() or _default_regulamento(regulamentos)
    regulamento = _obter_regulamento_por_arquivo(regulamentos, arquivo)
    if regulamento is None:
        raise FileNotFoundError("Regulamento pre-configurado nao encontrado.")
    return regulamento


def _nome_seguro(filename: str, *, fallback: str) -> str:
    nome = secure_filename(filename)
    return nome or fallback


def _resolver_regulamento_preset(config_dir: str | Path, filename: str) -> Path:
    nome = Path(filename).name
    caminho = Path(config_dir) / nome
    if not caminho.exists():
        raise FileNotFoundError("Regulamento selecionado nao foi encontrado no diretorio de configuracoes.")
    return caminho


def _preparar_regulamento_execucao_web(
    regulamento_path: str | Path,
    *,
    job_dir: str | Path,
) -> Path:
    caminho_origem = Path(regulamento_path)
    with caminho_origem.open("r", encoding="utf-8") as arquivo:
        regulamento = json.load(arquivo)

    verificacoes = dict(regulamento.get("verificacoes_automaticas") or {})
    if verificacoes:
        verificacoes["usar_openai_quando_disponivel"] = False
        verificacoes["timeout_segundos"] = min(
            float(verificacoes.get("timeout_segundos", 12) or 12),
            1.5,
        )
        verificacoes["max_download_bytes"] = min(
            int(verificacoes.get("max_download_bytes", 10 * 1024 * 1024) or 10 * 1024 * 1024),
            2 * 1024 * 1024,
        )
        verificacoes["max_recursos_remotos_por_execucao"] = min(
            int(
                verificacoes.get("max_recursos_remotos_por_execucao", 20)
                or 20
            ),
            20,
        )
        regulamento["verificacoes_automaticas"] = verificacoes

    caminho_destino = Path(job_dir) / "regulamento_execucao_web.json"
    caminho_destino.write_text(
        json.dumps(regulamento, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return caminho_destino


def _nome_saida(*, nome_acao: str, planilha_filename: str, modo: str = "ranqueamento") -> str:
    sufixo = "analise_regulamento" if modo == "analise_regulamento" else "ranking"
    if nome_acao:
        base = secure_filename(nome_acao)
        if base:
            return f"{base}_{sufixo}.xlsx"
    base_planilha = Path(_nome_seguro(planilha_filename, fallback="inscricoes.xlsx")).stem
    return f"{base_planilha}_{sufixo}.xlsx"


def _get_job_storage(app: Flask):
    return create_job_storage(
        backend=app.config["JOB_STORAGE_BACKEND"],
        local_storage_dir=app.config["STORAGE_DIR"],
        azure_container=app.config["AZURE_STORAGE_CONTAINER"],
        azure_account_url=app.config["AZURE_STORAGE_ACCOUNT_URL"],
        azure_connection_string=app.config["AZURE_STORAGE_CONNECTION_STRING"],
        azure_blob_prefix=app.config["AZURE_STORAGE_BLOB_PREFIX"],
    )


def _mensagem_falha_processamento(exc: Exception, *, aba: str | None) -> str:
    mensagem = str(exc)
    mensagem_normalizada = mensagem.lower()
    if "saida do proprio sistema de ranqueamento" in mensagem_normalizada:
        return mensagem
    if "worksheet" in mensagem_normalizada and "does not exist" in mensagem_normalizada:
        if aba:
            return (
                "Falha ao processar o ranqueamento: a aba informada nao existe neste arquivo. "
                "Tente limpar o campo 'Aba da planilha' ou informar o nome exato da aba."
            )
        return (
            "Falha ao processar o ranqueamento: o nome de aba configurado no regulamento nao existe "
            "neste arquivo. O sistema tentou usar a aba ativa, mas houve outro problema no carregamento."
        )
    if "regulamento pre-configurado nao encontrado" in mensagem_normalizada:
        return "Falha ao processar o ranqueamento: o regulamento selecionado nao foi encontrado."
    return f"Falha ao processar o ranqueamento: {mensagem}"


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
