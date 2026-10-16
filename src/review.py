"""Versões da minuta, aprovação humana vinculada a hash e versão vigente.

Regras:
- cada geração cria uma versão numerada e imutável (minuta e roteiro de leitura);
- a aprovação é por (caso, versão) e guarda o SHA-256 de minuta e roteiro;
- editar qualquer arquivo depois do registro invalida a aprovação;
- aprovação histórica e versão vigente (`versao_atual`) são conceitos distintos;
- nada aqui envia mensagem a cidadão.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.roteiro import gerar_roteiro_leitura, normalizar_quebras

CASO_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
DECISOES = {"aprovar", "rejeitar"}


class RevisaoError(Exception):
    """Erro de revisão ou de versão da minuta."""


class AprovacaoInvalidaError(RevisaoError):
    """Minuta sem aprovação válida para a versão exata dos arquivos."""


def validar_caso_id(caso_id: str) -> str:
    if not isinstance(caso_id, str) or not CASO_RE.match(caso_id):
        raise RevisaoError("Identificador de caso inválido; use letras, números, '_' ou '-'.")
    return caso_id


def hash_texto(texto: str) -> str:
    return hashlib.sha256(normalizar_quebras(texto).encode("utf-8")).hexdigest()


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


class Revisoes:
    def __init__(self, results_dir: Path | str):
        base = Path(results_dir)
        self.revisoes_dir = base / "revisoes"
        self.minutas_dir = base / "minutas"

    def _path(self, caso_id: str) -> Path:
        return self.revisoes_dir / f"{validar_caso_id(caso_id)}.json"

    def _load(self, caso_id: str) -> dict[str, Any]:
        path = self._path(caso_id)
        if not path.exists():
            return {
                "caso_id": caso_id,
                "versao_atual": None,
                "versoes": {},
                "decisoes": [],
                "solicitacoes_nova_geracao": [],
                "historico_vigente": [],
            }
        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, caso_id: str, registro: dict[str, Any]) -> None:
        path = self._path(caso_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def _arquivos(self, caso_id: str, versao: int) -> tuple[Path, Path]:
        return (
            self.minutas_dir / f"minuta_{caso_id}_v{versao}.txt",
            self.minutas_dir / f"roteiro_{caso_id}_v{versao}.txt",
        )

    def registrar_versao(self, caso_id: str, minuta_texto: str, roteiro_texto: str | None = None) -> int:
        """Cria a próxima versão. Nunca sobrescreve arquivos existentes."""
        validar_caso_id(caso_id)
        if not str(minuta_texto).strip():
            raise RevisaoError("A minuta está vazia.")
        registro = self._load(caso_id)
        versao = max((int(v) for v in registro["versoes"]), default=0) + 1
        roteiro = roteiro_texto if roteiro_texto is not None else gerar_roteiro_leitura(minuta_texto)
        minuta_path, roteiro_path = self._arquivos(caso_id, versao)
        self.minutas_dir.mkdir(parents=True, exist_ok=True)
        with minuta_path.open("x", encoding="utf-8") as handle:
            handle.write(minuta_texto)
        with roteiro_path.open("x", encoding="utf-8") as handle:
            handle.write(roteiro)
        registro["versoes"][str(versao)] = {
            "minuta_arquivo": minuta_path.name,
            "roteiro_arquivo": roteiro_path.name,
            "minuta_sha256": hash_texto(minuta_texto),
            "roteiro_sha256": hash_texto(roteiro),
            "criada_em": _agora(),
        }
        self._save(caso_id, registro)
        return versao

    def _versao_info(self, registro: dict[str, Any], versao: int) -> dict[str, Any]:
        info = registro["versoes"].get(str(versao))
        if info is None:
            raise RevisaoError(f"Versão {versao} não existe para o caso {registro['caso_id']}.")
        return info

    def _hashes_atuais(self, caso_id: str, versao: int) -> tuple[str, str]:
        minuta_path, roteiro_path = self._arquivos(caso_id, versao)
        if not minuta_path.exists() or not roteiro_path.exists():
            raise RevisaoError("Arquivo de minuta ou roteiro não encontrado.")
        return (
            hash_texto(minuta_path.read_text(encoding="utf-8")),
            hash_texto(roteiro_path.read_text(encoding="utf-8")),
        )

    def registrar_decisao(
        self,
        caso_id: str,
        versao: int,
        decisao: str,
        justificativa: str,
        operador: str,
        tornar_vigente: bool = False,
    ) -> dict[str, Any]:
        if decisao not in DECISOES:
            raise RevisaoError("Decisão inválida; use aprovar ou rejeitar.")
        if not (justificativa or "").strip():
            raise RevisaoError("Informe a justificativa da decisão humana.")
        if not (operador or "").strip():
            raise RevisaoError("Informe o operador responsável pela decisão.")
        registro = self._load(caso_id)
        info = self._versao_info(registro, versao)
        minuta_hash, roteiro_hash = self._hashes_atuais(caso_id, versao)
        if (minuta_hash, roteiro_hash) != (info["minuta_sha256"], info["roteiro_sha256"]):
            raise RevisaoError("Minuta ou roteiro foram alterados após o registro da versão; gere uma nova versão.")
        entrada = {
            "versao": versao,
            "decisao": decisao,
            "justificativa": justificativa.strip(),
            "operador": operador.strip(),
            "minuta_sha256": minuta_hash,
            "roteiro_sha256": roteiro_hash,
            "registrado_em": _agora(),
        }
        registro["decisoes"].append(entrada)
        if tornar_vigente and decisao == "aprovar":
            self._definir_vigente(registro, versao, operador.strip())
        self._save(caso_id, registro)
        return entrada

    def solicitar_nova_geracao(self, caso_id: str, versao_base: int, motivo: str, operador: str) -> dict[str, Any]:
        """Registra o pedido; a aprovação anterior permanece intacta."""
        if not (motivo or "").strip():
            raise RevisaoError("Informe o motivo da nova geração.")
        registro = self._load(caso_id)
        self._versao_info(registro, versao_base)
        entrada = {
            "versao_base": versao_base,
            "motivo": motivo.strip(),
            "operador": (operador or "").strip(),
            "registrado_em": _agora(),
        }
        registro["solicitacoes_nova_geracao"].append(entrada)
        self._save(caso_id, registro)
        return entrada

    def aprovacao_valida(self, caso_id: str, versao: int) -> bool:
        registro = self._load(caso_id)
        if str(versao) not in registro["versoes"]:
            return False
        decisoes = [item for item in registro["decisoes"] if item["versao"] == versao]
        if not decisoes or decisoes[-1]["decisao"] != "aprovar":
            return False
        try:
            minuta_hash, roteiro_hash = self._hashes_atuais(caso_id, versao)
        except RevisaoError:
            return False
        return (minuta_hash, roteiro_hash) == (decisoes[-1]["minuta_sha256"], decisoes[-1]["roteiro_sha256"])

    def _definir_vigente(self, registro: dict[str, Any], versao: int, operador: str) -> None:
        self._versao_info(registro, versao)
        registro["versao_atual"] = versao
        registro["historico_vigente"].append({"versao": versao, "operador": operador, "definida_em": _agora()})

    def definir_versao_atual(self, caso_id: str, versao: int, operador: str) -> None:
        if not (operador or "").strip():
            raise RevisaoError("Informe o operador que define a versão vigente.")
        registro = self._load(caso_id)
        self._definir_vigente(registro, versao, operador.strip())
        self._save(caso_id, registro)

    def versao_atual(self, caso_id: str) -> int | None:
        return self._load(caso_id)["versao_atual"]

    def resolver_versao(self, caso_id: str, versao: int | None = None, exigir_aprovacao: bool = True) -> int:
        """Resolve a versão de forma inequívoca; nunca adivinha."""
        if versao is None:
            versao = self.versao_atual(caso_id)
            if versao is None:
                raise RevisaoError(
                    "Nenhuma versão foi informada e não há versao_atual definida. "
                    "Use --versao N ou defina a vigente com o comando 'vigente'."
                )
        else:
            registro = self._load(caso_id)
            self._versao_info(registro, versao)
        if exigir_aprovacao and not self.aprovacao_valida(caso_id, versao):
            raise AprovacaoInvalidaError(
                f"A versão {versao} do caso {caso_id} não tem aprovação válida "
                "(não aprovada, rejeitada ou alterada após a aprovação)."
            )
        return versao

    def descrever_selecao(self, caso_id: str, versao: int) -> dict[str, Any]:
        """Dados exibidos ao operador antes de sintetizar voz."""
        registro = self._load(caso_id)
        info = self._versao_info(registro, versao)
        minuta_path, roteiro_path = self._arquivos(caso_id, versao)
        return {
            "caso_id": caso_id,
            "versao": versao,
            "vigente": registro["versao_atual"] == versao,
            "minuta": str(minuta_path),
            "roteiro": str(roteiro_path),
            "minuta_sha256": info["minuta_sha256"],
            "roteiro_sha256": info["roteiro_sha256"],
        }

    def ler_roteiro(self, caso_id: str, versao: int) -> str:
        """Retorna o roteiro aprovado, sem nenhuma transformação."""
        if not self.aprovacao_valida(caso_id, versao):
            raise AprovacaoInvalidaError("Roteiro sem aprovação válida.")
        return self._arquivos(caso_id, versao)[1].read_text(encoding="utf-8")

    def estado_atendimento(self, caso_id: str) -> str:
        """RECEBIDO, PENDENTE_REVISAO, APROVADO ou REJEITADO (PROCESSANDO é controlado pelo fluxo)."""
        registro = self._load(caso_id)
        if not registro["versoes"]:
            return "RECEBIDO"
        alvo = registro["versao_atual"] or max(int(v) for v in registro["versoes"])
        decisoes = [item for item in registro["decisoes"] if item["versao"] == alvo]
        if not decisoes:
            return "PENDENTE_REVISAO"
        if decisoes[-1]["decisao"] == "rejeitar":
            return "REJEITADO"
        return "APROVADO" if self.aprovacao_valida(caso_id, alvo) else "PENDENTE_REVISAO"
