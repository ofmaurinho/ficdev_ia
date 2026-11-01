# Decisões Técnicas

## 1. Separação de módulos e configuração

- `config.json` concentra modelos, temperaturas, limites de tokens, timeouts, caminhos e parâmetros do RAG (`top_k`, `similarity_threshold`, `max_calls_per_run`).
- `OPENAI_API_KEY` fica apenas em `.env` (ignorado pelo Git). `.env.example` documenta as variáveis sem valores reais.
- As regras de negócio ficam nos módulos de serviço (`src/nlp.py`, `src/rag.py`, `src/guardrails.py`, `src/sentiment.py`, `src/vector_store.py`, `src/metrics.py`). A CLI (`src/desafio2_cli.py`) e a interface Streamlit (`src/app.py`) apenas consomem esses serviços.

## 2. Escolha de modelos e bibliotecas

| Componente | Escolha | Motivo |
|---|---|---|
| Geração e extração estruturada | `gpt-4o-mini` (`Responses.parse`) | Suporte nativo a schema Pydantic estrito com baixo custo por chamada e `temperature=0`. |
| Embeddings | `text-embedding-3-small` (`1536` dim.) | Boa recuperação multilíngue (português e PDF em inglês `ACV-MATR-004`) no ChromaDB local. |
| Banco vetorial | `chromadb.PersistentClient` | Persistência local em disco (`dados/indice/chroma`), filtro por metadados e exclusão por `document_id`. |
| Leitura de PDF e OCR | `PyMuPDF` (acervo textual) / `pypdfium2` + Tesseract (OCR) | Extração de texto com número de página no acervo e OCR local antes de acionar Vision. |
| Áudio e imagem (Desafio 1) | `gpt-4o-transcribe`, `gpt-4o-mini-tts`, `gpt-image-2.5-flare` + Pillow | Transcrição com proveniência, leitura restrita a roteiro aprovado por hash e rótulo sintético composto localmente. |

## 3. Validação, RAG e sentimentos

- **Schema vs. regra de negócio (`RF14`):** `FichaSolicitacao` rejeita tipos inválidos e chaves extras via Pydantic; `validar_ficha()` verifica existência da data no calendário, suporte literal no texto, limite de 100 palavras no resumo e consistência de `campos_ausentes`.
- **Estratégia de chunking (`RF17`, `RF18`):** `structural` (17 chunks) e `fixed_400_overlap_80` (11 chunks) empataram em `5/5` no `hits@3`. Adotamos `structural` como padrão por manter seções inteiras e registrar o cabeçalho nos metadados.
- **Abstenção e conflito (`RF19`):** consultas com similaridade máxima abaixo de `0.40` param antes da geração (`sem_evidencia`). Divergências entre documentos vigentes de mesma prioridade retornam `conflito_de_fontes` sem escolher uma regra automaticamente.
- **Sentimentos (`RF22`):** o modelo classifica uma avaliação por vez (`positiva`, `negativa`, `neutra`, `indeterminada`), marcando ironia ou críticas mistas para revisão. Totais e percentuais são calculados em Python (`agregar_sentimentos()`).
- **Exclusão e auditoria (`RF23`, `RF24`):** a remoção de um documento em `src/vector_store.py` apaga seus chunks do ChromaDB e marca execuções RAG dependentes para revisão humana. Logs JSONL passam por sanitização central de chaves, CPFs e e-mails.
