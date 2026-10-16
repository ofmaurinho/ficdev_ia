from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

STATUS_VALIDADO = "VALIDADO_HUMANO"


class GabaritoInvalidoError(Exception):
    """Gabarito ausente, pendente ou incompleto."""


def sha256_arquivo(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for bloco in iter(lambda: handle.read(1 << 20), b""):
            digest.update(bloco)
    return digest.hexdigest()


def carregar_gabarito_validado(path: Path | str) -> dict[str, Any]:
    caminho = Path(path)
    if not caminho.exists():
        raise GabaritoInvalidoError(f"Gabarito não encontrado: {caminho.name}.")
    try:
        conteudo = json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GabaritoInvalidoError(f"Gabarito {caminho.name} não é um JSON válido: {exc.msg}.") from exc
    if not isinstance(conteudo, dict):
        raise GabaritoInvalidoError(f"Gabarito {caminho.name} deve ser um objeto JSON.")
    status = conteudo.get("status")
    if status != STATUS_VALIDADO:
        raise GabaritoInvalidoError(
            f"Gabarito {caminho.name} não está validado (status={status!r}). "
            f"A equipe deve preenchê-lo e definir status '{STATUS_VALIDADO}'."
        )
    for campo in ("elaborado_por", "data_elaboracao"):
        if not str(conteudo.get(campo, "")).strip():
            raise GabaritoInvalidoError(f"Gabarito {caminho.name} sem '{campo}'.")
    criticos = conteudo.get("campos_criticos")
    esperado = conteudo.get("resultado_esperado")
    if isinstance(criticos, dict) and criticos:
        vazios = [chave for chave, valor in criticos.items() if not str(valor).strip()]
        if vazios:
            raise GabaritoInvalidoError(f"Gabarito {caminho.name} com campos críticos vazios: {vazios}.")
    elif not (isinstance(esperado, dict) and esperado):
        raise GabaritoInvalidoError(f"Gabarito {caminho.name} sem campos_criticos nem resultado_esperado.")
    return {"conteudo": conteudo, "sha256": sha256_arquivo(caminho), "arquivo": caminho.name}


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args], capture_output=True, text=True, timeout=15, check=False
    )


def informacao_git(path: Path | str, repo_root: Path | str) -> dict[str, Any]:
    raiz = Path(repo_root).resolve()
    try:
        relativo = Path(path).resolve().relative_to(raiz).as_posix()
        log = _git(raiz, "log", "-1", "--format=%H|%cI", "--", relativo)
        status = _git(raiz, "status", "--porcelain", "--", relativo)
    except (ValueError, OSError, subprocess.SubprocessError):
        return {"git_disponivel": False, "commitado": False, "alterado_apos_commit": False}
    if log.returncode != 0 or not log.stdout.strip():
        return {"git_disponivel": log.returncode == 0, "commitado": False, "alterado_apos_commit": False}
    commit, data = log.stdout.strip().split("|", 1)
    return {
        "git_disponivel": True,
        "commitado": True,
        "commit": commit,
        "commit_data": data,
        "alterado_apos_commit": bool(status.stdout.strip()),
    }


def primeira_execucao_real(log_path: Path | str, arquivo_origem: str) -> str | None:
    caminho = Path(log_path)
    if not caminho.exists():
        return None
    primeira: str | None = None
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        try:
            evento = json.loads(linha)
        except json.JSONDecodeError:
            continue
        payload = evento.get("payload", {})
        if (
            evento.get("event_type") == "iniciado"
            and payload.get("arquivo_origem") == arquivo_origem
            and payload.get("provider") not in (None, "local")
        ):
            if primeira is None or evento["timestamp"] < primeira:
                primeira = evento["timestamp"]
    return primeira


def verificar_validade_temporal(
    gabarito_path: Path | str, repo_root: Path | str, log_path: Path | str, arquivo_origem: str
) -> dict[str, Any]:
    """Reúne evidências de que o gabarito antecede a primeira execução real."""
    info = informacao_git(gabarito_path, repo_root)
    avisos: list[str] = []
    if not info.get("commitado"):
        avisos.append("Gabarito não está commitado no Git; a data no JSON, sozinha, não comprova sua criação.")
    elif info["alterado_apos_commit"]:
        avisos.append("Gabarito foi alterado após o último commit.")
    primeira = primeira_execucao_real(log_path, arquivo_origem)
    info["primeira_execucao_real"] = primeira
    if primeira and info.get("commitado"):
        if datetime.fromisoformat(info["commit_data"]) > datetime.fromisoformat(primeira):
            avisos.append("O commit do gabarito é posterior à primeira execução real registrada.")
    info["avisos"] = avisos
    return info
