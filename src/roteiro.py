"""Roteiro de leitura canônico da minuta (determinístico, sem LLM).

O roteiro é gerado junto com cada versão da minuta, ANTES da revisão humana, e seu hash
é aprovado com a minuta. O TTS usa o roteiro sem nenhuma modificação posterior.
A função só remove marcações de formatação; nunca reescreve, resume ou acrescenta texto.
"""

from __future__ import annotations

import re
import unicodedata


def normalizar_quebras(texto: str) -> str:
    return unicodedata.normalize("NFC", texto).replace("\r\n", "\n").replace("\r", "\n")


def gerar_roteiro_leitura(minuta: str) -> str:
    if minuta is None or not str(minuta).strip():
        raise ValueError("A minuta está vazia; não é possível gerar o roteiro de leitura.")
    linhas: list[str] = []
    for linha in normalizar_quebras(str(minuta)).split("\n"):
        linha = re.sub(r"^\s{0,3}#{1,6}\s*", "", linha)
        linha = re.sub(r"^\s*[-*•]\s+", "", linha)
        linha = linha.replace("**", "").rstrip()
        linhas.append(linha)
    colapsado: list[str] = []
    for linha in linhas:
        if not linha and colapsado and not colapsado[-1]:
            continue
        colapsado.append(linha)
    return "\n".join(colapsado).strip() + "\n"
