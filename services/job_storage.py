from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any


@dataclass
class DownloadArquivo:
    nome_arquivo: str
    conteudo: bytes
    mime_type: str = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass
class JobMetadata:
    output_filename: str


class LocalJobStorage:
    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def create_job_workspace(self, job_id: str) -> Path:
        job_dir = self.root_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    def persist_job(self, job_id: str, workspace_dir: str | Path, output_filename: str) -> None:
        self._write_metadata(Path(workspace_dir), JobMetadata(output_filename=output_filename))

    def read_result(self, job_id: str) -> DownloadArquivo:
        job_dir = self.root_dir / job_id
        metadata = self._read_metadata(job_dir)
        output_path = job_dir / metadata.output_filename
        if not output_path.exists():
            raise FileNotFoundError("Arquivo de resultado nao encontrado no storage local.")
        return DownloadArquivo(
            nome_arquivo=metadata.output_filename,
            conteudo=output_path.read_bytes(),
        )

    def _metadata_path(self, job_dir: Path) -> Path:
        return job_dir / "metadata.json"

    def _write_metadata(self, job_dir: Path, metadata: JobMetadata) -> None:
        self._metadata_path(job_dir).write_text(
            json.dumps(metadata.__dict__, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

    def _read_metadata(self, job_dir: Path) -> JobMetadata:
        metadata_path = self._metadata_path(job_dir)
        if not metadata_path.exists():
            raise FileNotFoundError("Metadados do job nao encontrados no storage local.")
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        return JobMetadata(output_filename=payload["output_filename"])


class AzureBlobJobStorage:
    def __init__(
        self,
        *,
        container_name: str,
        account_url: str | None = None,
        connection_string: str | None = None,
        blob_prefix: str = "jobs",
    ) -> None:
        self.container_name = container_name
        self.blob_prefix = blob_prefix.strip("/").strip() or "jobs"
        self.workspace_root = Path(tempfile.gettempdir()) / "ranqueamento_jobs"
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.container_client = self._create_container_client(
            account_url=account_url,
            connection_string=connection_string,
        )

    def create_job_workspace(self, job_id: str) -> Path:
        job_dir = self.workspace_root / job_id
        if job_dir.exists():
            shutil.rmtree(job_dir)
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    def persist_job(self, job_id: str, workspace_dir: str | Path, output_filename: str) -> None:
        workspace = Path(workspace_dir)
        metadata = JobMetadata(output_filename=output_filename)
        metadata_path = workspace / "metadata.json"
        metadata_path.write_text(
            json.dumps(metadata.__dict__, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

        self.container_client.create_container()
        for caminho in workspace.rglob("*"):
            if not caminho.is_file():
                continue
            blob_name = self._blob_name(job_id, caminho.relative_to(workspace))
            with caminho.open("rb") as arquivo:
                self.container_client.upload_blob(blob_name, arquivo, overwrite=True)

        shutil.rmtree(workspace, ignore_errors=True)

    def read_result(self, job_id: str) -> DownloadArquivo:
        metadata_payload = self.container_client.download_blob(
            self._blob_name(job_id, "metadata.json")
        ).readall()
        metadata = JobMetadata(**json.loads(metadata_payload.decode("utf-8")))
        blob_name = self._blob_name(job_id, metadata.output_filename)
        conteudo = self.container_client.download_blob(blob_name).readall()
        return DownloadArquivo(nome_arquivo=metadata.output_filename, conteudo=conteudo)

    def _blob_name(self, job_id: str, relative_path: str | Path) -> str:
        relative = str(relative_path).replace("\\", "/").lstrip("/")
        return f"{self.blob_prefix}/{job_id}/{relative}"

    def _create_container_client(
        self,
        *,
        account_url: str | None,
        connection_string: str | None,
    ):
        try:
            from azure.storage.blob import BlobServiceClient
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Dependencias do Azure nao instaladas. Instale azure-identity e azure-storage-blob."
            ) from exc

        if connection_string:
            service_client = BlobServiceClient.from_connection_string(connection_string)
            return service_client.get_container_client(self.container_name)

        if not account_url:
            raise ValueError(
                "Para usar Azure Blob Storage, configure AZURE_STORAGE_CONNECTION_STRING "
                "ou AZURE_STORAGE_ACCOUNT_URL."
            )

        try:
            from azure.identity import DefaultAzureCredential
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Dependencia azure-identity nao instalada. Ela e necessaria para DefaultAzureCredential."
            ) from exc

        credential = DefaultAzureCredential()
        service_client = BlobServiceClient(account_url=account_url, credential=credential)
        return service_client.get_container_client(self.container_name)


def create_job_storage(
    *,
    backend: str,
    local_storage_dir: str | Path,
    azure_container: str | None = None,
    azure_account_url: str | None = None,
    azure_connection_string: str | None = None,
    azure_blob_prefix: str = "jobs",
):
    modo = (backend or "local").strip().lower()
    if modo == "local":
        return LocalJobStorage(local_storage_dir)
    if modo == "azure_blob":
        if not azure_container:
            raise ValueError("AZURE_STORAGE_CONTAINER e obrigatorio para o backend azure_blob.")
        return AzureBlobJobStorage(
            container_name=azure_container,
            account_url=azure_account_url,
            connection_string=azure_connection_string,
            blob_prefix=azure_blob_prefix,
        )
    raise ValueError(f"Backend de storage nao suportado: {backend}")
