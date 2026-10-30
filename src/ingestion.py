"""Extração página a página, metadados e chunking reproduzível do acervo autorizado."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class IngestionError(ValueError):
    """Documento não pode ser extraído/indexado com segurança."""


class OCRRequiredError(IngestionError):
    """PDF sem camada de texto; requer OCR anterior fora deste serviço."""


@dataclass(frozen=True)
class Fragment:
    document_id: str
    title: str
    version: str
    file_name: str
    file_sha256: str
    text: str
    page: int | None
    section: str | None
    section_id: str
    chunk_id: str
    chunking_strategy: str
    conflict_key: str | None = None
    conflict_value: str | None = None
    authority_rank: int | None = None
    effective_from: str | None = None
    effective_to: str | None = None

    def metadata(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if key not in {"text"} and value is not None}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _acervo_path(root: Path, directory: str | Path | None = None) -> Path:
    path = Path(directory) if directory is not None else Path("dados/originais/acervo")
    return (root / path).resolve() if not path.is_absolute() else path.resolve()


def carregar_manifesto(
    root: str | Path | None = None,
    *,
    acervo_directory: str | Path | None = None,
) -> list[dict[str, Any]]:
    base = Path(root) if root else Path(__file__).resolve().parent.parent
    path = _acervo_path(base, acervo_directory) / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    docs = manifest.get("documentos")
    if not isinstance(docs, list) or len({doc.get("document_id") for doc in docs}) != len(docs):
        raise IngestionError("O manifesto do acervo é inválido ou contém IDs duplicados.")
    return docs


def _path_from_manifest(entry: dict[str, Any], root: Path, acervo_directory: str | Path | None = None) -> Path:
    relative = Path(entry["file"])
    if relative.is_absolute():
        raise IngestionError("O manifesto deve conter caminhos relativos ao projeto.")
    allowed = _acervo_path(root, acervo_directory)
    resolved = (allowed / relative).resolve()
    try:
        resolved.relative_to(allowed)
    except ValueError as exc:
        raise IngestionError("O documento do manifesto está fora do diretório de acervo autorizado.") from exc
    if not resolved.is_file():
        raise FileNotFoundError(f"Documento do acervo ausente: {relative.as_posix()}")
    return resolved


def _extract_pages(path: Path) -> list[tuple[int | None, str]]:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return [(None, path.read_text(encoding="utf-8"))]
    if suffix != ".pdf":
        raise IngestionError("Formato não aceito no acervo: use TXT UTF-8 ou PDF textual.")
    try:
        import pymupdf
    except ImportError as exc:
        raise IngestionError("PyMuPDF não está instalado; instale as dependências do Desafio 2 para ler PDFs.") from exc
    with pymupdf.open(path) as document:
        pages = [(index + 1, page.get_text("text").strip()) for index, page in enumerate(document)]
    if not any(text for _, text in pages):
        raise OCRRequiredError(f"O PDF {path.name} não tem camada de texto; a indexação requer OCR prévio.")
    return pages


_HEADING = re.compile(r"(?m)^\s*(?:#{1,3}\s+|(?:SE[ÇC][ÃA]O|CL[ÁA]USULA)\s+(?:[\w.-]+\s*[-–:.]?\s*))(?:\d+[.)-]?\s*)?(.+?)\s*$", re.I)


def _structural_units(text: str) -> list[tuple[str | None, str, str]]:
    """Retorna seção, ID estável legível da seção e parágrafo/unidade semântica."""
    heading_matches = list(_HEADING.finditer(text))
    if not heading_matches:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        return [(None, f"paragrafo-{index + 1:03d}", body) for index, body in enumerate(paragraphs)]
    units: list[tuple[str | None, str, str]] = []
    current_section: str | None = None
    current_id: str | None = None
    previous = 0
    counter = 0
    blocks: list[tuple[str | None, str, str]] = []
    for match in heading_matches:
        body = text[previous:match.start()].strip()
        if body:
            blocks.append((current_section, current_id or "introducao", body))
        current_section = match.group(1).strip()
        slug = re.sub(r"[^a-z0-9]+", "-", current_section.casefold()).strip("-")[:48] or "secao"
        current_id = f"sec-{slug}"
        previous = match.end()
    body = text[previous:].strip()
    if body:
        blocks.append((current_section, current_id or "introducao", body))
    for section, section_id, block in blocks:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", block) if part.strip()]
        for paragraph in paragraphs:
            counter += 1
            units.append((section, f"{section_id}-p{counter:03d}", paragraph))
    return units


def _fixed_units(text: str, size: int, overlap: int) -> list[tuple[str | None, str, str]]:
    if size < 80 or overlap < 0 or overlap >= size:
        raise ValueError("Chunk fixo requer size >= 80 e 0 <= overlap < size.")
    clean = text.strip()
    matches = list(_HEADING.finditer(clean))
    if not matches:
        blocks = [(None, "texto", clean)]
    else:
        blocks = []
        for index, heading in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(clean)
            title = heading.group(1).strip()
            body = clean[heading.end():end].strip()
            if body:
                slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:48] or "secao"
                blocks.append((title, f"sec-{slug}", body))
    step = size - overlap
    chunks = []
    for section, section_id, block in blocks:
        for start in range(0, len(block), step):
            body = block[start:start + size].strip()
            if body:
                chunks.append((section, f"{section_id}-chars-{start}-{start + len(body)}", body))
    return chunks


def chunk_document(
    entry: dict[str, Any],
    *,
    root: str | Path | None = None,
    strategy: str = "structural",
    size: int = 400,
    overlap: int = 80,
    acervo_directory: str | Path | None = None,
) -> list[Fragment]:
    base = Path(root) if root else Path(__file__).resolve().parent.parent
    path = _path_from_manifest(entry, base, acervo_directory)
    file_hash = sha256_file(path)
    result: list[Fragment] = []
    for page_number, page_text in _extract_pages(path):
        if not page_text.strip():
            continue
        units = _structural_units(page_text) if strategy == "structural" else _fixed_units(page_text, size, overlap)
        for section, section_id, body in units:
            prefix = f"Documento {entry['document_id']} — {entry['title']} — versão {entry['version']}"
            if section:
                prefix += f" — seção {section}"
            if page_number is not None:
                prefix += f" — página {page_number}"
            indexed_text = f"{prefix}\n{body}".strip()
            stable = "|".join((entry["document_id"], str(entry["version"]), file_hash, str(page_number or ""), section_id, body))
            chunk_id = "chunk-" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24]
            result.append(Fragment(
                document_id=entry["document_id"], title=entry["title"], version=str(entry["version"]),
                file_name=path.name, file_sha256=file_hash, text=indexed_text, page=page_number,
                section=section, section_id=section_id, chunk_id=chunk_id, chunking_strategy=strategy,
                conflict_key=entry.get("conflict_key"), conflict_value=entry.get("conflict_value"),
                authority_rank=entry.get("authority_rank"), effective_from=entry.get("effective_from"),
                effective_to=entry.get("effective_to"),
            ))
    return result


def chunk_corpus(
    *,
    root: str | Path | None = None,
    strategy: str = "structural",
    size: int = 400,
    overlap: int = 80,
    acervo_directory: str | Path | None = None,
) -> list[Fragment]:
    """Indexa exclusivamente os documentos enumerados no manifesto fictício."""
    base = Path(root) if root else Path(__file__).resolve().parent.parent
    return [fragment for entry in carregar_manifesto(base, acervo_directory=acervo_directory)
            for fragment in chunk_document(entry, root=base, strategy=strategy, size=size,
                                           overlap=overlap, acervo_directory=acervo_directory)]
