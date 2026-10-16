"""Registro de auditoria e rastreabilidade das execuções."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            lowered = str(key).lower()
            safe_usage_fields = {
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "cached_tokens",
                "reasoning_tokens",
                "cache_write_tokens",
            }
            sensitive_field = any(
                marker in lowered
                for marker in ("api_key", "secret", "password", "authorization", "header")
            ) or ("token" in lowered and lowered not in safe_usage_fields)
            if sensitive_field:
                continue
            sanitized[key] = _safe_value(item)
        return sanitized
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [_safe_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class AuditLogger:
    def __init__(self, log_dir: str = "resultados/logs"):
        self.log_dir = log_dir
        self.log_path = Path(log_dir) / "audit.jsonl"
        self.log_dir_path = Path(log_dir)
        self.log_dir_path.mkdir(parents=True, exist_ok=True)

    def log_event(self, event_type: str, status: str, payload: Optional[Dict[str, Any]] = None, *, execution_id: Optional[str] = None) -> str:
        safe_payload = _safe_value(payload or {})
        entry = {
            "execution_id": execution_id or str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "status": status,
            "payload": safe_payload,
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry["execution_id"]


class ExecutionAudit:
    def __init__(self, log_dir: str = "resultados/logs"):
        self.logger = AuditLogger(log_dir=log_dir)
        self.execution_id = str(uuid.uuid4())

    def start(self, **kwargs):
        return self.logger.log_event("iniciado", "iniciado", kwargs, execution_id=self.execution_id)

    def success(self, **kwargs):
        return self.logger.log_event("resultado", "sucesso", kwargs, execution_id=self.execution_id)

    def fail(self, **kwargs):
        return self.logger.log_event("resultado", "falha", kwargs, execution_id=self.execution_id)

    def revise(self, **kwargs):
        return self.logger.log_event("revisao", "revisao_pendente", kwargs, execution_id=self.execution_id)


ESTADOS_ARTEFATO = ("NAO_GERADO", "GERANDO", "GERADO", "FALHA")
TRANSICOES_ARTEFATO = {
    "NAO_GERADO": {"GERANDO"},
    "GERANDO": {"GERADO", "FALHA"},
    "GERADO": set(),
    "FALHA": {"GERANDO"},
}
TIPOS_ARTEFATO = (
    "transcricao",
    "texto_ocr",
    "estruturado",
    "minuta",
    "roteiro_leitura",
    "audio",
    "imagem",
)


class ArtefatoError(Exception):
    """Transição de estado ou registro de artefato inválido."""


class OriginalAlteradoError(ArtefatoError):
    """Um arquivo original registrado mudou de conteúdo."""


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for bloco in iter(lambda: handle.read(1 << 20), b""):
            digest.update(bloco)
    return digest.hexdigest()


class ArtifactRegistry:
    """Registra originais (com hash) e artefatos (com tipo, versão e estado) por caso."""

    def __init__(self, results_dir: Path | str, caso_id: str, base_dir: Path | str | None = None):
        self.base_dir = Path(base_dir).resolve() if base_dir else None
        self.path = Path(results_dir) / "artefatos" / f"{caso_id}.json"
        self.caso_id = caso_id

    def _load(self) -> dict[str, Any]:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {"caso_id": self.caso_id, "originais": [], "artefatos": {}}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(_safe_value(data), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def _referencia(self, path: Path) -> str:
        resolvido = path.resolve()
        if self.base_dir:
            try:
                return resolvido.relative_to(self.base_dir).as_posix()
            except ValueError:
                pass
        return path.name

    def registrar_original(self, path: Path | str) -> dict[str, Any]:
        """Registra o hash do arquivo de origem. Se ele mudar depois, levanta erro."""
        caminho = Path(path)
        if not caminho.exists():
            raise ArtefatoError(f"Arquivo original não encontrado: {caminho.name}.")
        referencia = self._referencia(caminho)
        sha = sha256_file(caminho)
        data = self._load()
        for item in data["originais"]:
            if item["arquivo"] == referencia:
                if item["sha256"] != sha:
                    raise OriginalAlteradoError(f"O original {referencia} foi alterado após o registro.")
                return item
        item = {
            "id": f"orig-{sha[:12]}",
            "arquivo": referencia,
            "sha256": sha,
            "tamanho_bytes": caminho.stat().st_size,
            "registrado_em": datetime.now(timezone.utc).isoformat(),
        }
        data["originais"].append(item)
        self._save(data)
        return item

    @staticmethod
    def _chave(tipo: str, versao: int) -> str:
        if tipo not in TIPOS_ARTEFATO:
            raise ArtefatoError(f"Tipo de artefato desconhecido: {tipo}.")
        return f"{tipo}:v{int(versao)}"

    def estado(self, tipo: str, versao: int = 1) -> str:
        item = self._load()["artefatos"].get(self._chave(tipo, versao))
        return item["estado"] if item else "NAO_GERADO"

    def _transitar(self, tipo: str, versao: int, novo: str, **meta: Any) -> dict[str, Any]:
        chave = self._chave(tipo, versao)
        data = self._load()
        item = data["artefatos"].setdefault(
            chave, {"tipo": tipo, "versao": int(versao), "estado": "NAO_GERADO", "tentativas": 0, "historico": []}
        )
        if novo not in TRANSICOES_ARTEFATO[item["estado"]]:
            raise ArtefatoError(f"Transição inválida para {chave}: {item['estado']} -> {novo}.")
        agora = datetime.now(timezone.utc).isoformat()
        item["estado"] = novo
        if novo == "GERANDO":
            item["tentativas"] += 1
        item["atualizado_em"] = agora
        item["historico"].append({"estado": novo, "em": agora})
        item.update(meta)
        self._save(data)
        return item

    def iniciar(self, tipo: str, versao: int = 1, **meta: Any) -> dict[str, Any]:
        return self._transitar(tipo, versao, "GERANDO", **meta)

    def concluir(self, tipo: str, versao: int = 1, arquivo: Path | str | None = None, **meta: Any) -> dict[str, Any]:
        if arquivo is not None:
            caminho = Path(arquivo)
            meta["arquivo"] = self._referencia(caminho)
            if caminho.exists():
                meta["sha256"] = sha256_file(caminho)
        return self._transitar(tipo, versao, "GERADO", **meta)

    def falhar(self, tipo: str, versao: int = 1, erro: str = "", **meta: Any) -> dict[str, Any]:
        return self._transitar(tipo, versao, "FALHA", erro=erro, **meta)
