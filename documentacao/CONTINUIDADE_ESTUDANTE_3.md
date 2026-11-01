# Continuidade do Desafio Prático 2 — Estudante 3

## Estado desta etapa

O escopo desta etapa foi RF14/RF15 e RF17/RF18/RF19/RF21, mais contratos/documentação de integração. Em 30/10/2026 houve chamadas reais ao modelo e ao endpoint de embeddings para executar os cenários fictícios; nenhum custo monetário foi calculado. A chave do `.env` não foi exibida nem modificada. Importar os módulos não instancia cliente OpenAI; o carregador `load_dotenv()` existente pode carregar variáveis no processo.

O acervo RAG aceita somente os seis arquivos enumerados em `dados/originais/acervo/manifest.json` (3 TXT, 3 PDFs textuais fictícios). Arquivos de aula, enunciados e editais presentes em `arquivos/` não entram no índice. Há seis solicitações fictícias em `dados/originais/solicitacoes/` e seus gabaritos em `dados/gabaritos/desafio2_solicitacoes.json` (4 completas, 1 incompleta, 1 ambígua). Uma reutiliza a transcrição revisada do Desafio 1. O TXT OCR herdado contém erros/ilegibilidade e pode ser lido como entrada, mas seus campos não foram promovidos a gabarito verdadeiro. Doze avaliações e três casos adversariais estão em arquivos separados em `dados/originais/avaliacoes/`; são dados de referência, não saídas de modelo.

### Módulos e contratos efetivamente disponíveis

- Desafio 1 preservado: `src/main.py`, `src/text_processing.py`, `src/audio.py`, `src/vision.py`, `src/review.py`, `src/audit.py`, `src/llm_client.py` e fluxos de imagem/minuta existentes.
- `src/schemas.py`: `FichaSolicitacao` (`solicitacao.v2`), `RespostaRAG`, `AnaliseSentimento`, `ResultadoGuardrail`, citações e validação de negócio; demonstração local JSON/schema.
- `src/nlp.py`: `processar_solicitacao()`, `processar_arquivo_solicitacao()`, `carregar_texto_solicitacao()`, `registrar_revisao_ficha()`, `avaliar_ficha()` e `avaliar_conjunto_solicitacoes()`. O serviço pode ler TXT revisado de áudio/OCR do Desafio 1; JSON legado sem o texto integral deve ser acompanhado do TXT correspondente.
- `src/ingestion.py`: `carregar_manifesto()`, `chunk_document()` e `chunk_corpus()`. TXT usa UTF-8; PDF usa `pymupdf.open()` e registra página humana desde a extração; PDF sem camada textual retorna `OCRRequiredError`.
- `src/vector_store.py`: `indexar_acervo()`, `search_chunks()`, `listar_documentos_indexados()`, `excluir_documento_acervo()` e `demonstrar_exclusao_documento()`. Usa `chromadb.PersistentClient`, embedding explícito, `get_or_create_collection` e distância cosine. Mudança de modelo/dimensão/estratégia sinaliza índice incompatível.
- `src/rag_evaluation.py`: `avaliar_chunking()` compara as cinco perguntas respondíveis em duas coleções persistentes, com o mesmo embedding/top-k e referências determinísticas de chunk, selecionando `structural` como estratégia padrão.
- `src/rag.py`: `consultar_rag()` e `registrar_revisao_rag()`. Retorna estados `fundamentada`, `sem_evidencia`, `conflito_de_fontes`, `revisao_humana`, fontes com excerto original e decisão humana pendente. A aprovação só é aceita para status fundamentada; não há envio externo.
- `src/guardrails.py`: `validar_arquivo_entrada()`, `avaliar_entrada_guardrail()`, `avaliar_recuperacao_guardrail()`, `avaliar_saida_guardrail()`, `validar_limites_execucao()` e `avaliar_casos_adversariais()`.
- `src/sentiment.py`: `classificar_avaliacao()`, `agregar_sentimentos()` e `avaliar_conjunto_sentimentos()`.
- `src/metrics.py`: `verificar_regras_negocio_t02()`, `verificar_agregacao_t13()`, `executar_regressao_desafio1()` e `gerar_matriz_testes_rf23()`.
- `src/app.py`: interface Streamlit em quatro abas integrada aos serviços acima.
- `src/desafio2_cli.py`: camada CLI sem UI com subcomandos `demonstrar-schema`, `indexar`, `listar`, `avaliar-recuperacao`, `compreender`, `avaliar-solicitacoes`, `consultar`, `revisar`, `revisar-ficha`, `avaliar-guardrails`, `classificar-sentimentos`, `excluir-documento`, `regressao` e `avaliar-integrado`.
- `src/llm_client.py`: foi estendido com `parse_structured()` usando `client.responses.parse()` e `create_embeddings()`; ambos são chamados apenas em funções de serviço após solicitação explícita.

## Situação final por requisito (01/11/2026)

| Requisito | Estado | Evidência e resultado |
|---|---|---|
| RF14 | Concluído | Schema `solicitacao.v2`, prompt `compreensao_solicitacao.v3`, validação pós-schema (T01 e T02 aprovados). |
| RF15 | Concluído | 6/6 categorias, 19/25 campos literais, 25/25 entidades literais após normalização (`resultados/avaliacao_nlp_desafio2.json`). Omissão no resumo de `SOL-001` mantida em revisão. |
| RF16 | Concluído | Guardrails de entrada, recuperação, saída e limites em `src/guardrails.py`; 3/3 casos adversariais e 4/4 controles T05 aprovados (`resultados/avaliacao_guardrails.json`). |
| RF17 | Concluído | 6 documentos do manifesto indexados no Chroma persistente (`17` chunks estruturais, reindexação sem duplicar). |
| RF18 | Concluído | Estratégia `structural` selecionada após comparação empírica (5/5 hits@3, preservação integral de seções). |
| RF19 | Concluído | 8/8 cenários RAG com status correto e citações verificadas (`resultados/avaliacao_cenarios_rag.json`). `RAG-05` marcada como `rejeitada` por omissão parcial. |
| RF20 | Concluído | Interface Streamlit implementada em `src/app.py` com 4 abas, exibição de `"não localizado"` e limpeza de arquivo temporário em `finally`. |
| RF21 | Concluído | Provedor configurável (`openai` / `simulated`), logs sanitizados em `resultados/logs/` e tratamento de falhas sem perda do índice. |
| RF22 | Concluído | 12/12 avaliações classificadas conforme o gabarito e agregadas deterministicamente em Python (`resultados/avaliacao_sentimentos.json`). |
| RF23 | Concluído | Matriz integrada T01–T15 com 15/15 testes aprovados (`resultados/matriz_testes_rf23.json`) e regressão das 3 entradas do Desafio 1 (`resultados/regressao_desafio1_desafio2.json`). |
| RF24 | Concluído | Exclusão de `ACV-ATEND-005` e derivados demonstrada (`resultados/demonstracao_exclusao_rf24.json`) e decisões humanas (`aprovada`, `rejeitada`, `revisar`) registradas com operador. |

A suíte automatizada conta com **169 testes** (`python -m unittest discover -s testes -v`), incluindo `testes/test_estudante3_desafio2.py`.

