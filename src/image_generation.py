"""Peça visual de orientação: imagem gerada por IA + composição local com Pillow.

A IA gera apenas o fundo ilustrativo (sem texto e sem pessoas reais). Texto institucional,
brasão e o rótulo de conteúdo sintético são sobrepostos localmente, para evitar erros de
texto gerado por modelo e garantir a identificação. A peça só é "utilizável" depois da
revisão visual humana registrada na nota de proveniência.
"""

from __future__ import annotations

import io
import json
import os
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.audit import sha256_file

ROTULO_PADRAO = "Gerado por IA — conteúdo sintético"
ITENS_REVISAO = ("texto", "simbolos", "maos", "objetos", "coerencia_visual")
FONTES_CANDIDATAS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
)
FONTES_NEGRITO = (
    *(p.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf") for p in FONTES_CANDIDATAS[:3]),
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
)


def montar_prompt(
    sujeito: str,
    composicao: str,
    estilo: str,
    iluminacao: str,
    proporcao: str,
    restricoes: list[str],
) -> str:
    """Prompt estruturado: sujeito, composição, estilo, iluminação, proporção e restrições."""
    campos = {
        "Sujeito": sujeito,
        "Composição": composicao,
        "Estilo": estilo,
        "Iluminação": iluminacao,
        "Proporção": proporcao,
    }
    vazios = [nome for nome, valor in campos.items() if not (valor or "").strip()]
    if vazios or not restricoes:
        raise ValueError(f"Prompt de imagem incompleto: faltam {vazios or ['Restrições']}.")
    linhas = [f"{nome}: {valor.strip()}" for nome, valor in campos.items()]
    linhas.append("Restrições: " + "; ".join(r.strip() for r in restricoes))
    return "\n".join(linhas)


PROMPT_PADRAO = montar_prompt(
    sujeito="Ilustração institucional acolhedora sobre matrícula em curso técnico: prancheta, calendário e ícones de saúde (cruz, estetoscópio), sem pessoas.",
    composicao="Elementos centralizados, espaço livre no terço superior e inferior para texto sobreposto.",
    estilo="Ilustração vetorial plana, paleta azul e verde sóbria, aspecto de comunicação pública.",
    iluminacao="Luz difusa e uniforme, sem sombras fortes.",
    proporcao="Quadrada, 1:1.",
    restricoes=[
        "nenhum texto, letras ou números na imagem",
        "nenhuma pessoa, rosto ou mão",
        "nenhum brasão, logotipo ou símbolo oficial",
        "sem marcas d'água",
    ],
)


def _fonte(tamanho: int, negrito: bool = False):
    from PIL import ImageFont

    for caminho in FONTES_NEGRITO if negrito else FONTES_CANDIDATAS:
        if Path(caminho).exists():
            return ImageFont.truetype(caminho, tamanho)
    return ImageFont.load_default(size=tamanho)


def compor_peca(
    imagem_base: bytes,
    *,
    titulo: str,
    texto: str,
    out_path: Path | str,
    brasao_path: Path | str | None = None,
    rotulo: str = ROTULO_PADRAO,
    lado: int = 1024,
) -> Path:
    """Sobrepõe cabeçalho com brasão, texto de orientação e rótulo de conteúdo sintético."""
    from PIL import Image, ImageDraw

    base = Image.open(io.BytesIO(imagem_base)).convert("RGB").resize((lado, lado))
    desenho = ImageDraw.Draw(base, "RGBA")
    faixa = int(lado * 0.17)
    desenho.rectangle([0, 0, lado, faixa], fill=(12, 45, 87, 235))
    margem = int(lado * 0.04)
    x_texto = margem
    if brasao_path and Path(brasao_path).exists():
        with Image.open(brasao_path) as brasao:
            brasao = brasao.convert("RGBA")
            altura = faixa - 2 * int(margem * 0.6)
            brasao.thumbnail((altura, altura))
            base.paste(brasao, (margem, int(margem * 0.6)), brasao)
            x_texto = margem + brasao.width + margem
    fonte_titulo = _fonte(int(lado * 0.045), negrito=True)
    for i, linha in enumerate(textwrap.wrap(titulo, width=34)[:2]):
        desenho.text((x_texto, int(margem * 0.9) + i * int(lado * 0.055)), linha, font=fonte_titulo, fill=(255, 255, 255))

    caixa_topo = int(lado * 0.60)
    desenho.rectangle([margem, caixa_topo, lado - margem, lado - int(lado * 0.10)], fill=(255, 255, 255, 225))
    fonte_texto = _fonte(int(lado * 0.034))
    y = caixa_topo + int(margem * 0.6)
    for linha in textwrap.wrap(texto, width=46):
        if y > lado - int(lado * 0.10) - int(lado * 0.045):
            break
        desenho.text((margem * 1.5, y), linha, font=fonte_texto, fill=(20, 20, 20))
        y += int(lado * 0.045)

    rodape = lado - int(lado * 0.075)
    desenho.rectangle([0, rodape, lado, lado], fill=(0, 0, 0, 215))
    desenho.text((margem, rodape + int(lado * 0.018)), rotulo, font=_fonte(int(lado * 0.032), negrito=True), fill=(255, 214, 10))

    destino = Path(out_path)
    destino.parent.mkdir(parents=True, exist_ok=True)
    base.save(destino, format="PNG")
    return destino


def gerar_imagem(
    prompt: str,
    *,
    client,
    image_cfg: dict[str, Any] | None = None,
    titulo: str,
    texto: str,
    out_path: Path | str,
    caso_id: str = "caso",
    brasao_path: Path | str | None = None,
    base_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Gera a imagem de fundo, compõe a peça e grava a nota de proveniência (revisão pendente)."""
    cfg = image_cfg or {}
    modelo = cfg.get("model", "gpt-image-2.5-flare")
    resposta = client.generate_image(
        prompt, model=modelo, size=cfg.get("size", "1024x1024"), quality=cfg.get("quality", "medium")
    )
    destino = compor_peca(
        resposta["image_bytes"],
        titulo=titulo,
        texto=texto,
        out_path=out_path,
        brasao_path=brasao_path,
        rotulo=cfg.get("rotulo", ROTULO_PADRAO),
    )
    destino_fundo = Path(str(destino).replace(".png", "_fundo_ia.png"))
    destino_fundo.write_bytes(resposta["image_bytes"])
    nota = {
        "caso_id": caso_id,
        "tipo": "gerada_por_ia",
        "identificacao": cfg.get("rotulo", ROTULO_PADRAO),
        "arquivo_peca": destino.name,
        "arquivo_peca_sha256": sha256_file(destino),
        "arquivo_fundo_ia": destino_fundo.name,
        "arquivo_fundo_sha256": sha256_file(destino_fundo),
        "prompt": prompt,
        "modelo": modelo,
        "parametros": {"size": cfg.get("size", "1024x1024"), "quality": cfg.get("quality", "medium")},
        "gerada_em": datetime.now(timezone.utc).isoformat(),
        "elementos_sobrepostos_localmente": ["titulo", "texto_orientacao", "brasao", "rotulo_sintetico"],
        "brasao_origem": Path(brasao_path).name if brasao_path else None,
        "pessoa_real": False,
        "metadata": resposta["metadata"],
        "revisao_visual": {"status": "pendente", "itens": {item: None for item in ITENS_REVISAO}},
        "utilizavel": False,
    }
    nota_path = Path(str(destino) + ".proveniencia.json")
    _salvar(nota_path, nota)
    return nota


def _salvar(path: Path, dados: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def registrar_revisao_visual(
    nota_path: Path | str, operador: str, itens: dict[str, bool], observacao: str = ""
) -> dict[str, Any]:
    """Registra a revisão visual. A peça só fica utilizável se todos os itens forem aprovados."""
    if not (operador or "").strip():
        raise ValueError("Informe o operador responsável pela revisão visual.")
    faltando = [i for i in ITENS_REVISAO if i not in itens]
    if faltando:
        raise ValueError(f"Itens de revisão visual não avaliados: {faltando}.")
    caminho = Path(nota_path)
    nota = json.loads(caminho.read_text(encoding="utf-8"))
    if sha256_file(caminho.with_name(nota["arquivo_peca"])) != nota["arquivo_peca_sha256"]:
        raise ValueError("A imagem foi alterada após a geração; a revisão não pode ser registrada.")
    aprovada = all(bool(itens[i]) for i in ITENS_REVISAO)
    nota["revisao_visual"] = {
        "status": "aprovada" if aprovada else "reprovada",
        "itens": {i: bool(itens[i]) for i in ITENS_REVISAO},
        "operador": operador.strip(),
        "observacao": observacao.strip(),
        "revisada_em": datetime.now(timezone.utc).isoformat(),
    }
    nota["utilizavel"] = aprovada
    _salvar(caminho, nota)
    return nota
