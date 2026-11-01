#!/usr/bin/env python3
"""Verificação pré-entrega do protótipo FIC_DEV — Desafio Prático 1.

Uso:
    python scripts/verificar_entrega.py

Sai com código 0 se tudo estiver OK, ou 1 se houver itens faltando.
Não requer dependências além da biblioteca padrão.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OK = "  ✅"
FAIL = "  ❌"
WARN = "  ⚠ "

falhas: list[str] = []
avisos: list[str] = []


def _ok(msg: str) -> None:
    print(f"{OK} {msg}")


def _fail(msg: str) -> None:
    print(f"{FAIL} {msg}")
    falhas.append(msg)


def _warn(msg: str) -> None:
    print(f"{WARN} {msg}")
    avisos.append(msg)


def _run(*cmd: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(cmd),
        capture_output=True,
        text=True,
        cwd=str(cwd or ROOT),
        timeout=120,
    )


# ---------------------------------------------------------------------------
# 1. Estrutura de arquivos obrigatórios
# ---------------------------------------------------------------------------

def verificar_estrutura() -> None:
    print("\n── 1. Estrutura de arquivos ──────────────────────────────────")
    obrigatorios = [
        "src/main.py",
        "src/llm_client.py",
        "src/audio.py",
        "src/vision.py",
        "src/image_generation.py",
        "src/review.py",
        "src/roteiro.py",
        "src/gabarito.py",
        "src/evaluation.py",
        "src/campos.py",
        "src/audit.py",
        "src/text_processing.py",
        "src/prompts.py",
        "prompts/system.txt",
        "prompts/prompt_a.txt",
        "prompts/prompt_b.txt",
        "config.json",
        "requirements.txt",
        "requirements.lock",
        ".env.example",
        ".gitignore",
        "dados/gabaritos/entrada_texto.json",
        "dados/gabaritos/entrada_audio.json",
        "dados/gabaritos/entrada_pdf-imagem.json",
        "dados/gabaritos/entrada_texto_injecao.json",
        "arquivos/entrada_texto.txt",
        "arquivos/entrada_audio.mp3",
        "arquivos/entrada_pdf-imagem.pdf",
        "arquivos/entrada_texto_injecao.txt",
        "documentacao/decisoes_tecnicas.md",
        "documentacao/registro_uso_ia.md",
        "src/schemas.py",
        "src/nlp.py",
        "src/guardrails.py",
        "src/ingestion.py",
        "src/vector_store.py",
        "src/rag.py",
        "src/rag_evaluation.py",
        "src/sentiment.py",
        "src/metrics.py",
        "src/app.py",
        "src/desafio2_cli.py",
        "dados/originais/acervo/manifest.json",
        "dados/gabaritos/desafio2_solicitacoes.json",
        "dados/gabaritos/desafio2_rag.json",
        "resultados/avaliacao_nlp_desafio2.json",
        "resultados/avaliacoes_recuperacao.json",
        "resultados/avaliacao_cenarios_rag.json",
        "resultados/avaliacao_guardrails.json",
        "resultados/avaliacao_sentimentos.json",
        "resultados/demonstracao_exclusao_rf24.json",
        "resultados/regressao_desafio1_desafio2.json",
        "resultados/matriz_testes_rf23.json",
    ]
    for rel in obrigatorios:
        p = ROOT / rel
        if p.exists():
            _ok(rel)
        else:
            _fail(f"Arquivo obrigatório ausente: {rel}")


# ---------------------------------------------------------------------------
# 2. Gabaritos validados
# ---------------------------------------------------------------------------

def verificar_gabaritos() -> None:
    print("\n── 2. Gabaritos ──────────────────────────────────────────────")
    gabaritos_dir = ROOT / "dados" / "gabaritos"
    jsons = list(gabaritos_dir.glob("*.json"))
    if not jsons:
        _fail("Nenhum gabarito encontrado em dados/gabaritos/")
        return
    for gab_path in sorted(jsons):
        try:
            conteudo = json.loads(gab_path.read_text("utf-8"))
            status = conteudo.get("status", "")
            elaborado = conteudo.get("elaborado_por", "").strip()
            data = conteudo.get("data_elaboracao", "").strip()
            if status == "VALIDADO_HUMANO" and elaborado and data:
                _ok(f"{gab_path.name} — VALIDADO_HUMANO por {elaborado}")
            else:
                _warn(f"{gab_path.name} — status={status!r} (ainda pendente)")
        except (json.JSONDecodeError, OSError) as exc:
            _fail(f"{gab_path.name}: {exc}")


# ---------------------------------------------------------------------------
# 3. Gabaritos commitados antes da execução real
# ---------------------------------------------------------------------------

def verificar_gabaritos_git() -> None:
    print("\n── 3. Gabaritos no Git ───────────────────────────────────────")
    log_path = ROOT / "resultados" / "logs" / "audit.jsonl"
    gabaritos_dir = ROOT / "dados" / "gabaritos"

    for gab_path in sorted(gabaritos_dir.glob("*.json")):
        rel = gab_path.relative_to(ROOT).as_posix()
        result = _run("git", "log", "-1", "--format=%H|%cI", "--", rel)
        if result.returncode != 0 or not result.stdout.strip():
            _warn(f"{gab_path.name}: não commitado no Git")
            continue
        commit, data_commit = result.stdout.strip().split("|", 1)

        # Verifica alteração após commit
        status = _run("git", "status", "--porcelain", "--", rel)
        if status.stdout.strip():
            _warn(f"{gab_path.name}: alterado após o último commit ({commit[:8]})")
        else:
            _ok(f"{gab_path.name}: commitado em {data_commit[:10]} ({commit[:8]})")

        # Compara com primeira execução real
        if log_path.exists():
            primeira = _primeira_execucao_real(log_path, gab_path.stem)
            if primeira and data_commit > primeira:
                _fail(f"{gab_path.name}: commit ({data_commit[:19]}) POSTERIOR à primeira execução real ({primeira[:19]})")


def _primeira_execucao_real(log_path: Path, arquivo_stem: str) -> str | None:
    primeira: str | None = None
    for linha in log_path.read_text("utf-8").splitlines():
        try:
            ev = json.loads(linha)
        except json.JSONDecodeError:
            continue
        payload = ev.get("payload", {})
        origem = str(payload.get("arquivo_origem", ""))
        if (
            ev.get("event_type") == "iniciado"
            and arquivo_stem in origem
            and payload.get("provider") not in (None, "local")
        ):
            ts = ev.get("timestamp", "")
            if primeira is None or ts < primeira:
                primeira = ts
    return primeira


# ---------------------------------------------------------------------------
# 4. Testes automatizados
# ---------------------------------------------------------------------------

def verificar_testes() -> None:
    print("\n── 4. Testes automatizados ───────────────────────────────────")
    result = _run(sys.executable, "-m", "unittest", "discover", "-s", "testes", "-v")
    linhas = (result.stdout + result.stderr).splitlines()
    resumo = next((l for l in reversed(linhas) if l.startswith("Ran ")), "")
    if result.returncode == 0:
        _ok(f"Testes: {resumo}")
    else:
        _fail(f"Falha nos testes: {resumo}")
        for linha in linhas:
            if "FAIL" in linha or "ERROR" in linha:
                print(f"     {linha}")


# ---------------------------------------------------------------------------
# 5. Instalação em venv limpo
# ---------------------------------------------------------------------------

def verificar_venv_limpo() -> None:
    print("\n── 5. Instalação em venv limpo ───────────────────────────────")
    with tempfile.TemporaryDirectory() as td:
        venv_dir = Path(td) / "venv_check"
        venv.create(str(venv_dir), with_pip=True, clear=True)
        pip = venv_dir / "bin" / "pip"
        python = venv_dir / "bin" / "python"

        r = subprocess.run(
            [str(pip), "install", "-r", str(ROOT / "requirements.txt"), "--quiet"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=300,
        )
        if r.returncode != 0:
            _fail(f"pip install falhou:\n{r.stderr[-500:]}")
            return

        r = subprocess.run(
            [str(pip), "check"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        if r.returncode == 0:
            _ok("pip check OK no venv limpo")
        else:
            _fail(f"pip check falhou:\n{r.stdout}")


# ---------------------------------------------------------------------------
# 6. Comandos CLI respondem a --help
# ---------------------------------------------------------------------------

def verificar_cli() -> None:
    print("\n── 6. CLI (--help) ───────────────────────────────────────────")
    result = _run(sys.executable, "-m", "src.main", "--help")
    if result.returncode == 0:
        _ok("python -m src.main --help")
    else:
        _fail(f"--help falhou: {result.stderr[:200]}")

    comandos = [
        "processar-texto", "prompts", "revisar", "logs",
        "audio", "ocr", "imagem", "voz", "aprovar-minuta", "avaliar",
        "fluxo", "vigente", "relatorio",
    ]
    help_text = result.stdout + result.stderr
    for cmd in comandos:
        if cmd in help_text:
            _ok(f"  comando '{cmd}' documentado")
        else:
            _warn(f"  comando '{cmd}' não encontrado no --help")

    result_d2 = _run(sys.executable, "-m", "src.desafio2_cli", "--help")
    if result_d2.returncode == 0:
        _ok("python -m src.desafio2_cli --help")
    else:
        _fail(f"desafio2_cli --help falhou: {result_d2.stderr[:200]}")

    comandos_d2 = [
        "indexar", "avaliar-recuperacao", "compreender", "avaliar-solicitacoes",
        "consultar", "revisar", "revisar-ficha", "avaliar-guardrails",
        "classificar-sentimentos", "excluir-documento", "regressao",
        "avaliar-integrado", "demonstrar-schema", "listar",
    ]
    help_d2 = result_d2.stdout + result_d2.stderr
    for cmd in comandos_d2:
        if cmd in help_d2:
            _ok(f"  comando Desafio 2 '{cmd}' documentado")
        else:
            _fail(f"  comando Desafio 2 '{cmd}' não encontrado no --help")


# ---------------------------------------------------------------------------
# 7. Resultados reais de execução
# ---------------------------------------------------------------------------

def verificar_resultados_reais() -> None:
    print("\n── 7. Resultados reais de execução ───────────────────────────")
    resultados_dir = ROOT / "resultados"
    log_path = resultados_dir / "logs" / "audit.jsonl"

    # Verifica se há execuções reais no log (provider != local)
    if not log_path.exists():
        _warn("Log de auditoria ausente — execuções reais ainda não realizadas")
        return

    modalidades_reais: set[str] = set()
    for linha in log_path.read_text("utf-8").splitlines():
        try:
            ev = json.loads(linha)
        except json.JSONDecodeError:
            continue
        payload = ev.get("payload", {})
        if ev.get("event_type") == "iniciado" and payload.get("provider") not in (None, "local"):
            modalidades_reais.add(payload.get("modalidade", "desconhecida"))

    esperadas = {"texto", "audio", "ocr", "tts", "imagem"}
    for mod in sorted(esperadas):
        if mod in modalidades_reais:
            _ok(f"Execução real registrada: {mod}")
        else:
            _warn(f"Execução real pendente: {mod}")

    # Verifica caso aprovado e caso rejeitado
    revisoes_dir = resultados_dir / "revisoes"
    if revisoes_dir.exists():
        aprovados = rejeitados = 0
        for f in revisoes_dir.glob("*.json"):
            try:
                dados = json.loads(f.read_text("utf-8"))
                for d in dados.get("decisoes", []):
                    if d.get("decisao") == "aprovar":
                        aprovados += 1
                    elif d.get("decisao") == "rejeitar":
                        rejeitados += 1
            except (json.JSONDecodeError, OSError):
                continue
        if aprovados > 0:
            _ok(f"Caso(s) aprovado(s): {aprovados}")
        else:
            _warn("Nenhum caso aprovado registrado")
        if rejeitados > 0:
            _ok(f"Caso(s) rejeitado(s)/corrigido(s): {rejeitados}")
        else:
            _warn("Nenhum caso rejeitado registrado (RF13)")
    else:
        _warn("Diretório de revisões ausente — aprovação ainda não realizada")


# ---------------------------------------------------------------------------
# 8. Peça visual com rótulo sintético
# ---------------------------------------------------------------------------

def verificar_imagem() -> None:
    print("\n── 8. Peça visual ────────────────────────────────────────────")
    minutas_dir = ROOT / "resultados" / "minutas"
    if not minutas_dir.exists():
        _warn("resultados/minutas/ ausente")
        return

    pecas = list(minutas_dir.glob("peca_*.png"))
    provenencias = list(minutas_dir.glob("*.proveniencia.json"))

    if pecas:
        _ok(f"Peça visual encontrada: {pecas[0].name}")
    else:
        _warn("Nenhuma peça visual gerada ainda (peca_*.png)")

    for prov_path in provenencias:
        try:
            prov = json.loads(prov_path.read_text("utf-8"))
            rotulo = prov.get("identificacao", "")
            utilizavel = prov.get("utilizavel", False)
            if "conteúdo sintético" in rotulo.lower() or "sintetico" in rotulo.lower():
                _ok(f"Rótulo sintético presente: {rotulo!r}")
            else:
                _fail(f"Rótulo sintético ausente ou incorreto em {prov_path.name}")
            if utilizavel:
                _ok("Revisão visual registrada como aprovada")
            else:
                _warn(f"Revisão visual pendente em {prov_path.name}")
        except (json.JSONDecodeError, OSError) as exc:
            _warn(f"Falha ao ler {prov_path.name}: {exc}")


# ---------------------------------------------------------------------------
# 9. Varredura de segredos
# ---------------------------------------------------------------------------

def verificar_segredos() -> None:
    print("\n── 9. Varredura de segredos ──────────────────────────────────")
    padroes_chave = [
        (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "Chave OpenAI (sk-...)"),
        (re.compile(r"Bearer [A-Za-z0-9_.-]{20,}"), "Bearer token"),
    ]
    # CPF e e-mail fictícios conhecidos (não são segredos)
    dados_ficticios = {
        "123.456.789-00", "987.654.321-00",
        "marcos.almeida.teste@examplo.com",
        "marcos.almeida.teste@exemplo.com",
        "anacarolina.ficdev@exemplo.com",
    }
    extensoes_texto = {".py", ".json", ".txt", ".md", ".jsonl", ".lock", ".toml", ".cfg", ".ini"}
    ignorar = {".venv", ".git", "__pycache__", ".mypy_cache", ".ruff_cache"}

    encontrados: list[str] = []
    for caminho in ROOT.rglob("*"):
        if any(parte in ignorar for parte in caminho.parts):
            continue
        if not caminho.is_file() or caminho.suffix not in extensoes_texto:
            continue
        if caminho.name == ".env":
            continue  # nunca deve existir com credenciais
        try:
            conteudo = caminho.read_text("utf-8", errors="ignore")
        except OSError:
            continue
        rel = caminho.relative_to(ROOT).as_posix()
        for padrao, nome in padroes_chave:
            for m in padrao.finditer(conteudo):
                encontrados.append(f"{rel}: {nome} — {m.group()[:20]}...")

    if encontrados:
        for item in encontrados:
            _fail(f"Segredo detectado: {item}")
    else:
        _ok("Nenhum segredo detectado nos arquivos de texto")

    # Verifica .env fora do .gitignore
    env_path = ROOT / ".env"
    gitignore = (ROOT / ".gitignore").read_text("utf-8") if (ROOT / ".gitignore").exists() else ""
    if env_path.exists():
        _warn(".env existe localmente — verificar se está no .gitignore")
    if ".env" in gitignore:
        _ok(".env coberto pelo .gitignore")
    else:
        _fail(".env não está no .gitignore")


# ---------------------------------------------------------------------------
# 10. Documentação
# ---------------------------------------------------------------------------

def verificar_documentacao() -> None:
    print("\n── 10. Documentação ──────────────────────────────────────────")
    docs = [
        ("documentacao/decisoes_tecnicas.md", "Decisões técnicas"),
        ("documentacao/registro_uso_ia.md", "Registro de uso de IA"),
        ("documentacao/relatorio_tecnico.md", "Relatório técnico"),
        ("documentacao/acessibilidade_e_soberania.md", "Acessibilidade e soberania"),
        ("documentacao/roteiro_apresentacao.md", "Roteiro de apresentação"),
        ("documentacao/matriz_avaliacao_prompts.md", "Matriz de avaliação de prompts"),
    ]
    for rel, nome in docs:
        p = ROOT / rel
        if p.exists() and p.stat().st_size > 100:
            _ok(f"{nome}: {rel}")
        elif p.exists():
            _warn(f"{nome}: arquivo muito curto ({p.stat().st_size} bytes) — {rel}")
        else:
            _warn(f"{nome}: ausente — {rel}")

    # Verifica roteiro de apresentação com tempo total
    roteiro_path = ROOT / "documentacao" / "roteiro_apresentacao.md"
    if roteiro_path.exists():
        conteudo = roteiro_path.read_text("utf-8")
        # Captura apenas tempos de bloco principal: "Bloco X — Título (N min)"
        minutos = re.findall(r"Bloco\s+\d+[^(]*\((\d+)\s*min\)", conteudo)
        total = sum(int(m) for m in minutos)
        if total > 0:
            if total <= 12:
                _ok(f"Tempo total do roteiro: {total} min (≤ 12 min)")
            else:
                _warn(f"Tempo total do roteiro: {total} min (excede 12 min)")



# ---------------------------------------------------------------------------
# 11. .env.example
# ---------------------------------------------------------------------------

def verificar_env_example() -> None:
    print("\n── 11. .env.example ──────────────────────────────────────────")
    p = ROOT / ".env.example"
    if not p.exists():
        _fail(".env.example ausente")
        return
    conteudo = p.read_text("utf-8")
    if re.search(r"sk-[A-Za-z0-9_-]{10,}", conteudo):
        _fail(".env.example contém credencial real!")
    else:
        _ok(".env.example sem credenciais reais")
    if "OPENAI_API_KEY" in conteudo:
        _ok(".env.example documenta OPENAI_API_KEY")
    else:
        _warn(".env.example não menciona OPENAI_API_KEY")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 60)
    print("  VERIFICAÇÃO PRÉ-ENTREGA — FIC_DEV Desafio Prático 1")
    print("=" * 60)

    verificar_estrutura()
    verificar_gabaritos()
    verificar_gabaritos_git()
    verificar_testes()
    verificar_cli()
    verificar_resultados_reais()
    verificar_imagem()
    verificar_segredos()
    verificar_documentacao()
    verificar_env_example()

    print("\n" + "=" * 60)
    if falhas:
        print(f"  RESULTADO: {len(falhas)} falha(s), {len(avisos)} aviso(s)")
        print("  Corrija as falhas antes de compactar.")
        for f in falhas:
            print(f"    ❌ {f}")
        return 1
    elif avisos:
        print(f"  RESULTADO: OK com {len(avisos)} aviso(s)")
        print("  Verifique os avisos — podem representar etapas pendentes.")
        return 0
    else:
        print("  RESULTADO: TUDO OK — pode compactar para entrega.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
