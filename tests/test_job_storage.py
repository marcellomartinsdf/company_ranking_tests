from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.job_storage import create_job_storage


class JobStorageTestCase(unittest.TestCase):
    def test_local_storage_deve_persistir_e_recuperar_resultado(self) -> None:
        with tempfile.TemporaryDirectory() as diretorio_temporario:
            storage = create_job_storage(
                backend="local",
                local_storage_dir=diretorio_temporario,
            )
            workspace = storage.create_job_workspace("job-1")
            arquivo_saida = workspace / "ranking.xlsx"
            arquivo_saida.write_bytes(b"conteudo-teste")

            storage.persist_job("job-1", workspace, "ranking.xlsx")
            resultado = storage.read_result("job-1")

            self.assertEqual(resultado.nome_arquivo, "ranking.xlsx")
            self.assertEqual(resultado.conteudo, b"conteudo-teste")


if __name__ == "__main__":
    unittest.main()
