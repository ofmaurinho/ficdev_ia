# Relatório Técnico — Central Inteligente de Atendimento e Comunicação Institucional

**Equipe:** FIC_DEV — Programador de Sistemas com IA  
**Projeto:** Desafios Práticos 1 e 2 — Inteligência Artificial Generativa (Aulas 01 a 14)  
**Versão:** 2.0 — 2026

## 1. Visão geral

O protótipo organiza a triagem de solicitações fictícias recebidas em texto, áudio e imagem/PDF, valida dados por schema e regras de negócio, consulta um acervo institucional local via RAG, analisa avaliações de atendimento e gera minutas sujeitas à decisão de um operador humano. Nenhuma resposta é enviada automaticamente ao cidadão.

| Módulo | Arquivo | Papel principal |
|---|---|---|
| Cliente de provedor | `src/llm_client.py`, `src/providers.py` | Chamadas OpenAI (texto, parse estruturado, embeddings, STT, TTS, Vision, imagem) e provedor simulado |
| Fluxo multimodal (Desafio 1) | `src/text_processing.py`, `src/audio.py`, `src/vision.py`, `src/image_generation.py`, `src/review.py`, `src/roteiro.py` | Extração textual, STT/TTS, OCR Tesseract + fallback Vision, peça visual sintética e aprovação por hash SHA-256 |
| Schemas e NLP (`RF14`, `RF15`) | `src/schemas.py`, `src/nlp.py` | Contrato `FichaSolicitacao` (`solicitacao.v2`), validação pós-schema, classificação, resumo (até 100 palavras) e entidades literais |
| Guardrails (`RF16`) | `src/guardrails.py` | Controles de entrada, recuperação e saída, limite `max_calls_per_run = 5` e bloqueio de injeção/exfiltração |
| Ingestão, índice e RAG (`RF17`–`RF19`) | `src/ingestion.py`, `src/vector_store.py`, `src/rag.py`, `src/rag_evaluation.py` | Leitura restrita ao manifesto, chunking (`structural` e `fixed_400_overlap_80`), ChromaDB persistente, busca cosseno, citações e abstenção |
| Sentimentos e métricas (`RF22`, `RF23`) | `src/sentiment.py`, `src/metrics.py` | Classificação individual de avaliações, agregação determinística em Python, regressão do Desafio 1 e matriz `T01`–`T15` |
| Interfaces e auditoria (`RF20`, `RF21`, `RF24`) | `src/app.py`, `src/desafio2_cli.py`, `src/main.py`, `src/audit.py` | Painel Streamlit em 4 abas, CLIs e logs JSONL sem segredos |

## 2. Decisões de arquitetura

1. **Operação desacoplada do gabarito:** o fluxo normal funciona sem ler gabaritos; os arquivos em `dados/gabaritos/` são usados apenas nos comandos de avaliação.
2. **Validação em duas etapas (`RF14`):** o JSON retornado pelo modelo passa primeiro pelo Pydantic estrito (`extra="forbid"`) e depois por `validar_ficha()` em `src/schemas.py` (datas reais no calendário, suporte literal no texto de origem, limite de 100 palavras no resumo e bloqueio de minuta quando faltam campos críticos ou o pedido é ambíguo).
3. **Aprovação vinculada a hash e estado:** no Desafio 1, a aprovação de minuta e roteiro é atrelada ao SHA-256 antes de liberar o TTS; no Desafio 2, fichas e consultas RAG preservam os estados `pendente`, `aprovada`, `rejeitada` e `revisar`, exigindo identificação do operador e justificativa.
4. **RAG restrito ao manifesto (`RF17`–`RF19`):** apenas os 6 documentos listados em `dados/originais/acervo/manifest.json` entram no índice. Quando a maior similaridade fica abaixo de `0.40`, o sistema se abstém sem chamar o modelo gerador. Quando dois documentos vigentes divergem (ex.: `ACV-MATR-002` e `ACV-MATR-006`), o retorno assume estado `conflito_de_fontes` para decisão humana.
5. **Distinção entre estimativa e cálculo determinístico (`RF22`):** o modelo classifica cada avaliação individualmente, mas todas as contagens, percentuais e taxas de revisão são calculados em Python (`agregar_sentimentos()`), com deduplicação por `id`.

## 3. Modelos e parâmetros

| Tarefa | Modelo | Parâmetros principais |
|---|---|---|
| Compreensão NLP, RAG e sentimentos | `gpt-4o-mini` | `temperature=0`, `max_output_tokens=700`/`800`, `max_calls_per_run=5` |
| Embeddings do acervo | `text-embedding-3-small` | `1536` dimensões, distância cosseno (`1 - distância`) |
| Transcrição de áudio (STT) | `gpt-4o-transcribe` | `language="pt"` |
| Síntese de voz (TTS) | `gpt-4o-mini-tts` | `voice="alloy"`, apenas sobre roteiro aprovado |
| OCR (fallback Vision) | `gpt-4o-mini` | `max_tokens=2000` por página quando o OCR local aciona gatilho |
| Geração de imagem | `gpt-image-2.5-flare` | `1024x1024`, composição de texto e rótulo sintético via Pillow |

## 4. Resultados medidos

- **Compreensão de solicitações (`resultados/avaliacao_nlp_desafio2.json`):** `6/6` categorias corretas, `19/25` campos literais, `25/25` entidades literais e `6/20` correspondências lexicais diretas nos resumos. `SOL-001` ficou em `revisar` porque o resumo omitiu a regra de faltas dos primeiros dias; `SOL-005` (incompleta) e `SOL-006` (ambígua) tiveram a minuta bloqueada.
- **Guardrails (`resultados/avaliacao_guardrails.json`):** `3/3` ataques adversariais (`ADV-01`, `ADV-02`, `ADV-03`) contidos e `4/4` testes de controle (escopo, tamanho, extensão e limite de chamadas) aprovados.
- **Segmentação e RAG (`resultados/avaliacoes_recuperacao.json`, `resultados/avaliacao_cenarios_rag.json`):** `5/5` hits@3 nas duas estratégias (`structural` com 17 chunks e `fixed_400_overlap_80` com 11 chunks). Nos 8 cenários RAG: `8/8` status esperados (`5` fundamentadas com citações válidas, `2` abstenções sem chamar geração e `1` conflito). Na revisão humana, `RAG-02`, `RAG-03` e `RAG-04` foram aprovadas, `RAG-05` foi rejeitada por omitir o encaminhamento à coordenação e `RAG-01`, `RAG-06`, `RAG-07` e `RAG-08` ficaram em `revisar`.
- **Sentimentos (`resultados/avaliacao_sentimentos.json`):** `12/12` avaliações classificadas conforme o gabarito (`3` positivas, `3` negativas, `3` neutras e `3` indeterminadas encaminhadas para revisão).
- **Exclusão, regressão e matriz `T01`–`T15` (`resultados/matriz_testes_rf23.json`):** exclusão de `ACV-ATEND-005` removeu seus chunks da busca (`2` antes, `0` após exclusão) e invalidou execuções RAG dependentes; `3/3` entradas herdadas do Desafio 1 rodaram sem regressão; `15/15` testes da matriz integrada e `170` testes unitários passaram.

## 5. Segurança, privacidade e limitações

- **Dados fictícios e minimização:** todo o acervo, solicitações e avaliações são fictícios. Dados pessoais são minimizados antes do envio ao provedor e nunca aparecem nos logs (`resultados/logs/audit.jsonl` e `resultados/logs/consultas.jsonl`). Credenciais ficam apenas em `.env` (ignorado pelo Git).
- **Limitações conhecidas:** a amostra de avaliação é pequena (6 solicitações, 8 perguntas RAG e 12 avaliações); o limiar de similaridade `0.40` foi ajustado para este conjunto fictício; a confiança numérica de sentimento vem do modelo e não é probabilidade calibrada; o projeto registra tokens e latência, mas não calcula custo financeiro por não fixar tabela de preços.
