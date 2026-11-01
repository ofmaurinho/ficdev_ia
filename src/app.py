"""Interface Streamlit local para o assistente institucional (RF20)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from src.guardrails import avaliar_entrada_guardrail, validar_arquivo_entrada
from src.ingestion import IngestionError, OCRRequiredError, _extract_pages, carregar_manifesto
from src.metrics import gerar_matriz_testes_rf23
from src.nlp import (
    carregar_texto_solicitacao,
    processar_solicitacao,
    registrar_revisao_ficha,
)
from src.rag import consultar_rag, registrar_revisao_rag
from src.sentiment import agregar_sentimentos, avaliar_conjunto_sentimentos
from src.vector_store import (
    IndexErrorRAG,
    excluir_documento_acervo,
    indexar_acervo,
    listar_documentos_indexados,
)

ROOT = Path(__file__).resolve().parent.parent
NAO_LOCALIZADO = "não localizado"


def carregar_config() -> dict[str, Any]:
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def formatar_campo_interface(valor: Any) -> str:
    """Converte null ou string vazia para 'não localizado' na interface (RF14/RF20)."""
    if valor is None:
        return NAO_LOCALIZADO
    texto = str(valor).strip()
    return texto if texto else NAO_LOCALIZADO


def validar_upload_documento(
    nome_arquivo: str,
    conteudo_bytes: bytes,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Valida upload em memória usando arquivo temporário para PDF e limpando no finally."""
    sufixo = Path(nome_arquivo).suffix.lower()
    if sufixo not in {".txt", ".pdf"}:
        raise IngestionError("Formato não permitido. Envie arquivo .txt ou .pdf textual.")
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=sufixo) as tmp:
            tmp.write(conteudo_bytes)
            tmp_path = Path(tmp.name)
        guard = validar_arquivo_entrada(tmp_path, extensoes_permitidas={".txt", ".pdf"}, config=config)
        if guard.decisao == "bloquear":
            raise IngestionError(f"Arquivo rejeitado pelos guardrails: {', '.join(guard.motivos)}")
        paginas = _extract_pages(tmp_path)
        texto_total = "\n\n".join(t for _, t in paginas if t)
        guard_txt = avaliar_entrada_guardrail(texto_total, max_chars=80_000, config=config)
        if guard_txt.decisao != "permitir":
            raise IngestionError(f"Conteúdo do documento retido pelos guardrails: {', '.join(guard_txt.motivos)}")
        return {"nome": nome_arquivo, "paginas": len(paginas), "caracteres": len(texto_total)}
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def render_app() -> None:
    import pandas as pd
    import streamlit as st

    st.set_page_config(page_title="Central Inteligente de Atendimento", layout="wide")
    st.title("Central Inteligente de Atendimento e Comunicação Institucional")
    st.caption("Protótipo local assistido por IA — todas as minutas exigem revisão humana antes de qualquer envio.")

    config = carregar_config()
    d2 = config.get("desafio2", {})

    with st.sidebar:
        st.header("Configuração")
        provedor = st.selectbox(
            "Provedor de geração (RF21)",
            options=["openai", "simulated"],
            index=0 if d2.get("generation", {}).get("provider", "openai") == "openai" else 1,
        )
        config["desafio2"]["generation"]["provider"] = provedor
        estrategia = st.selectbox(
            "Estratégia de chunking (RF18)",
            options=["structural", "fixed_400_overlap_80"],
            index=0,
        )
        config["desafio2"]["chunking"]["strategy_selected"] = estrategia
        top_k = st.slider("Top-k da busca vetorial", min_value=1, max_value=6, value=int(d2.get("retrieval", {}).get("top_k", 3)))
        operador = st.text_input("Identificação do operador", value="servidor_atendimento")
        st.info("Similaridade exibida = 1 - distância cosine. Valor alto indica proximidade vetorial, não garantia de verdade.")

    aba_acervo, aba_sol, aba_rag, aba_sent = st.tabs([
        "1. Acervo e Índice (RF17/RF24)",
        "2. Solicitações e NLP (RF14/RF15)",
        "3. Consulta RAG e Revisão (RF19/RF20)",
        "4. Sentimentos e Métricas (RF22/RF23)",
    ])

    with aba_acervo:
        st.subheader("Acervo Institucional e Índice Persistente")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Documentos autorizados no manifesto**")
            manifesto = carregar_manifesto(ROOT)
            st.dataframe(pd.DataFrame(manifesto)[["document_id", "title", "version", "file", "topic"]], use_container_width=True)
            if st.button("Indexar / Atualizar Acervo"):
                with st.spinner("Calculando embeddings e atualizando ChromaDB..."):
                    try:
                        info = indexar_acervo(strategy=estrategia, config=config)
                        st.success(f"Índice atualizado: {info['total_chunks']} trechos na coleção {info['collection']}.")
                    except Exception as exc:
                        st.error(f"Falha ao indexar acervo: {exc}")

        with col2:
            st.markdown("**Documentos presentes no índice persistente**")
            try:
                indexados = listar_documentos_indexados(strategy=estrategia, config=config)
                if indexados:
                    st.dataframe(pd.DataFrame(indexados), use_container_width=True)
                else:
                    st.warning("O índice está vazio para esta estratégia. Clique em 'Indexar / Atualizar Acervo'.")
            except IndexErrorRAG as exc:
                st.error(f"Índice incompatível ou desatualizado: {exc}")

            st.divider()
            st.markdown("**Exclusão de documento e derivados (RF24)**")
            doc_excluir = st.selectbox("Selecionar documento para remover do índice", [d["document_id"] for d in manifesto])
            if st.button("Excluir documento do índice"):
                evento = excluir_documento_acervo(doc_excluir, remover_derivados=False, config=config)
                st.warning(f"Documento {doc_excluir} removido ({evento['chunks_removed']} chunks excluídos).")

            st.divider()
            st.markdown("**Validar novo documento (.txt ou .pdf textual)**")
            upload_doc = st.file_uploader("Selecionar arquivo para verificação", type=["txt", "pdf"])
            if upload_doc is not None and st.button("Validar documento enviado"):
                try:
                    res_up = validar_upload_documento(upload_doc.name, upload_doc.getvalue())
                    st.success(f"Documento válido: {res_up['paginas']} página(s), {res_up['caracteres']} caracteres.")
                except (IngestionError, OCRRequiredError) as exc:
                    st.error(str(exc))

    with aba_sol:
        st.subheader("Compreensão, Extração e Validação de Solicitações")
        sol_dir = ROOT / "dados" / "originais" / "solicitacoes"
        arquivos_sol = sorted(sol_dir.glob("SOL-*.txt")) + [
            ROOT / "dados" / "processados" / "entrada_audio_transcricao_revisada.txt",
            ROOT / "dados" / "processados" / "entrada_pdf_ocr_corrigido.txt",
        ]
        opcoes_sol = {p.name: p for p in arquivos_sol if p.exists()}
        escolha = st.selectbox("Escolher solicitação existente", list(opcoes_sol.keys()))
        texto_inicial = carregar_texto_solicitacao(opcoes_sol[escolha]) if escolha else ""
        texto_sol = st.text_area("Texto da solicitação", value=texto_inicial, height=140)
        sol_id = escolha.split("_")[0] if escolha.startswith("SOL-") else Path(escolha).stem

        if st.button("Compreender e Validar Solicitação"):
            with st.spinner("Extraindo ficha estruturada e aplicando regras de negócio..."):
                try:
                    saida = processar_solicitacao(texto_sol, solicitacao_id=sol_id, config=config)
                    st.session_state["ultima_ficha"] = saida
                except Exception as exc:
                    st.error(f"Bloqueado na validação/guardrail: {exc}")

        ficha_atual = st.session_state.get("ultima_ficha")
        if not ficha_atual:
            ficha_salva = ROOT / "dados" / "processados" / f"{sol_id}_ficha.json"
            if ficha_salva.is_file():
                ficha_atual = json.loads(ficha_salva.read_text(encoding="utf-8"))

        if ficha_atual:
            ficha = ficha_atual["ficha"]
            c1, c2, c3 = st.columns(3)
            c1.metric("Protocolo", formatar_campo_interface(ficha.get("protocolo")))
            c2.metric("Data", formatar_campo_interface(ficha.get("data")))
            c3.metric("Categoria", formatar_campo_interface(ficha.get("categoria")))

            st.write("**Solicitante:**", formatar_campo_interface(ficha.get("solicitante")))
            st.write("**Assunto:**", formatar_campo_interface(ficha.get("assunto")))
            st.write("**Pedido:**", formatar_campo_interface(ficha.get("pedido")))
            st.write("**Resumo (até 100 palavras):**", ficha.get("resumo"))
            st.write("**Campos ausentes:**", ", ".join(ficha.get("campos_ausentes") or []) or "nenhum")
            st.write("**Status:**", ficha_atual.get("status"), "| **Decisão humana:**", ficha_atual.get("decisao_humana", "pendente"))

            if ficha_atual.get("alertas_negocio"):
                for alerta in ficha_atual["alertas_negocio"]:
                    st.warning(alerta)

            if ficha.get("entidades"):
                st.markdown("**Entidades literais extraídas**")
                st.dataframe(pd.DataFrame(ficha["entidades"]), use_container_width=True)

            if ficha_atual.get("minuta"):
                st.text_area("Minuta preliminar (rascunho sujeito a revisão)", value=ficha_atual["minuta"], height=180)
            else:
                st.info("Minuta automática bloqueada por ausência de campo crítico ou alerta de revisão.")

            with st.form("form_revisao_ficha"):
                dec_ficha = st.selectbox("Decisão sobre a ficha", ["revisar", "aprovada", "rejeitada"])
                just_ficha = st.text_input("Justificativa da decisão")
                if st.form_submit_button("Registrar decisão da ficha"):
                    try:
                        atualizado = registrar_revisao_ficha(sol_id, dec_ficha, just_ficha, operador=operador, config=config)
                        st.session_state["ultima_ficha"] = atualizado
                        st.success(f"Decisão '{dec_ficha}' registrada para {sol_id}.")
                    except Exception as exc:
                        st.error(str(exc))

    with aba_rag:
        st.subheader("Consulta Fundamentada ao Acervo (RAG) e Revisão Humana")
        gab_rag = json.loads((ROOT / "dados" / "gabaritos" / "desafio2_rag.json").read_text(encoding="utf-8"))["perguntas_avaliacao"]
        perguntas_opcoes = ["(Digitar consulta livre)"] + [f"{q['id']} — {q['pergunta']}" for q in gab_rag]
        escolha_q = st.selectbox("Perguntas de referência ou consulta livre", perguntas_opcoes)
        pergunta_padrao = "" if escolha_q == "(Digitar consulta livre)" else escolha_q.split(" — ", 1)[1]
        pergunta = st.text_input("Pergunta ao acervo institucional", value=pergunta_padrao)

        if st.button("Consultar Acervo"):
            with st.spinner("Buscando trechos no ChromaDB e gerando resposta fundamentada..."):
                res_rag = consultar_rag(pergunta, config=config, top_k=top_k, strategy=estrategia)
                st.session_state["ultimo_rag"] = res_rag

        rag_atual = st.session_state.get("ultimo_rag")
        if rag_atual:
            status_rag = rag_atual.get("status")
            st.markdown(f"**Execução:** `{rag_atual.get('execution_id')}` | **Status:** `{status_rag}` | **Provedor:** `{rag_atual.get('provider')}` | **Decisão:** `{rag_atual.get('human_decision')}`")
            if status_rag == "fundamentada":
                st.success("Resposta fundamentada nos trechos recuperados (aguardando revisão humana).")
                st.text_area("Minuta / Resposta fundamentada", value=rag_atual.get("answer") or "", height=140)
            elif status_rag == "sem_evidencia":
                st.warning(rag_atual.get("message") or "Sem evidência suficiente no acervo.")
            elif status_rag == "conflito_de_fontes":
                st.error(rag_atual.get("message") or "Conflito entre fontes vigentes; encaminhado para revisão humana.")
                if rag_atual.get("conflict"):
                    st.json(rag_atual["conflict"])
            else:
                st.warning(rag_atual.get("message") or "Encaminhado para revisão humana.")

            fontes = rag_atual.get("sources") or []
            if fontes:
                st.markdown("**Trechos recuperados (metadados verificados na extração)**")
                for src in fontes:
                    titulo_exp = (
                        f"{src['document_id']} (v{src['version']}) | chunk={src['chunk_id']} | "
                        f"página={formatar_campo_interface(src.get('page'))} | seção={formatar_campo_interface(src.get('section'))} | "
                        f"similaridade={src['similarity']:.3f} (distância={src['distance']:.3f})"
                    )
                    with st.expander(titulo_exp):
                        st.text(src["excerpt"])

            with st.form("form_revisao_rag"):
                opcoes_dec = ["aprovada", "rejeitada", "revisar"] if status_rag == "fundamentada" else ["revisar", "rejeitada"]
                dec_rag = st.selectbox("Decisão do operador", opcoes_dec)
                just_rag = st.text_input("Justificativa da revisão")
                if st.form_submit_button("Registrar decisão humana"):
                    try:
                        rev = registrar_revisao_rag(
                            rag_atual["execution_id"],
                            dec_rag,
                            just_rag,
                            operator=operador,
                            config=config,
                        )
                        st.session_state["ultimo_rag"] = rev
                        st.success(f"Decisão '{dec_rag}' persistida no artefato e no log de auditoria.")
                    except Exception as exc:
                        st.error(str(exc))

    with aba_sent:
        st.subheader("Painel de Sentimentos (RF22) e Matriz Integrada (RF23)")
        caminho_sent = ROOT / "resultados" / "avaliacao_sentimentos.json"
        if st.button("Reexecutar Classificação das 12 Avaliações"):
            with st.spinner("Classificando avaliações fictícias..."):
                avaliar_conjunto_sentimentos(config=config)

        if caminho_sent.is_file():
            dados_sent = json.loads(caminho_sent.read_text(encoding="utf-8"))
            itens_sent = dados_sent.get("resultados", [])
            filtro_pol = st.selectbox("Filtrar por polaridade", ["(Todas)", "positiva", "negativa", "neutra", "indeterminada"])
            so_revisao = st.checkbox("Mostrar apenas casos que exigem revisão humana")
            pol_arg = None if filtro_pol == "(Todas)" else filtro_pol
            agr = agregar_sentimentos(itens_sent, filtro_polaridade=pol_arg, apenas_revisao=so_revisao)

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total considerado (denominador)", agr["denominador"])
            acc = agr["acuracia_gabarito"]
            m2.metric("Acerto frente ao gabarito", f"{acc['numerador']}/{acc['denominador']}")
            rev_m = agr["casos_para_revisao"]
            m3.metric("Casos para revisão", f"{rev_m['numerador']}/{rev_m['denominador']}")
            m4.metric("Duplicatas removidas", agr["duplicatas_removidas"])

            st.caption(agr["nota_metodologica"])
            df_contagem = pd.DataFrame([
                {"polaridade": k, "quantidade": v, "proporcao": agr["proporcoes"][k]["proporcao"]}
                for k, v in agr["contagem_por_polaridade"].items()
            ])
            st.bar_chart(df_contagem.set_index("polaridade")["quantidade"])

            linhas_tabela = []
            for item in itens_sent:
                an = item["analise"]
                if pol_arg and an["polaridade"] != pol_arg:
                    continue
                if so_revisao and not an["revisao_necessaria"]:
                    continue
                linhas_tabela.append({
                    "ID": item["id"],
                    "Texto": item["texto"],
                    "Gabarito": item["rotulo_gabarito"],
                    "Polaridade": an["polaridade"],
                    "Revisão": an["revisao_necessaria"],
                    "Confiança (não calibrada)": an["confianca_modelo"],
                    "Justificativa": an["justificativa"],
                })
            st.dataframe(pd.DataFrame(linhas_tabela), use_container_width=True)

        st.divider()
        st.subheader("Matriz de Testes Obrigatórios (T01 a T15 — RF23)")
        caminho_matriz = ROOT / "resultados" / "matriz_testes_rf23.json"
        if st.button("Atualizar Matriz Integrada RF23") or not caminho_matriz.is_file():
            gerar_matriz_testes_rf23(config=config)
        if caminho_matriz.is_file():
            matriz = json.loads(caminho_matriz.read_text(encoding="utf-8"))
            st.dataframe(pd.DataFrame(matriz.get("testes_obrigatorios", [])), use_container_width=True)


if __name__ == "__main__":
    render_app()
