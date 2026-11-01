# Central Inteligente de Atendimento e Comunicação Institucional

Protótipo local para triagem de solicitações fictícias em texto, áudio e imagem/PDF, consulta fundamentada ao acervo institucional (RAG), análise de avaliações de atendimento e geração de minutas sujeitas à revisão humana.

## Divisão da equipe

- **Estudante 1:** schemas estruturados, compreensão de solicitações (NLP), gabaritos e documentação.
- **Estudante 2:** ingestão do acervo, busca vetorial (ChromaDB), RAG com citações e auditoria.
- **Estudante 3:** áudio (STT/TTS), OCR/visão, geração de imagem, guardrails, painel de sentimentos, interface Streamlit e avaliação integrada.

## Estrutura de pastas

- `arquivos/`: entradas multimodais herdadas do Desafio 1 (`entrada_texto.txt`, `entrada_audio.mp3`, `entrada_pdf-imagem.pdf`, `entrada_texto_injecao.txt`, `brasao.png`).
- `dados/originais/acervo/`: 6 documentos institucionais fictícios controlados por `manifest.json`.
- `dados/originais/solicitacoes/`: 6 solicitações fictícias para extração e classificação (`SOL-001` a `SOL-006`).
- `dados/originais/avaliacoes/`: 12 avaliações fictícias e 3 casos adversariais.
- `dados/gabaritos/`: gabaritos validados do Desafio 1 e do Desafio 2.
- `dados/processados/`: fichas extraídas (`.json`) e transcrições/OCR revisados (`.txt`).
- `resultados/`: relatórios de avaliação (`.json`), execuções RAG (`resultados/rag/`), minutas (`resultados/minutas/`) e logs sanitizados (`resultados/logs/`).
- `src/`: código-fonte da central, CLI e interface Streamlit.
- `prompts/`: templates de prompt versionados.
- `documentacao/`: relatórios técnicos, decisões e roteiro de apresentação.
- `testes/`: suíte de testes automatizados (`170` testes).

## Pré-requisitos e instalação

- Python 3.10+ (validado em Python 3.12 / 3.14).
- Tesseract OCR com pacote de idioma `por` instalado no sistema.
- Chave da OpenAI configurada em `.env` (copie de `.env.example`) para chamadas reais de LLM, embeddings, STT, TTS, Vision e imagem.

Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Windows (PowerShell):
```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
Copy-Item .env.example .env
$env:PYTHONUTF8 = "1"
```

## Comandos principais

### Desafio 1 — Fluxo multimodal (`src/main.py`)

```bash
python -m src.main --help
python -m src.main processar-texto --arquivo arquivos/entrada_texto.txt
python -m src.main prompts --arquivo arquivos/entrada_texto.txt
python -m src.main audio --arquivo arquivos/entrada_audio.mp3 --caso entrada_audio
python -m src.main ocr --arquivo arquivos/entrada_pdf-imagem.pdf --caso entrada_pdf
python -m src.main aprovar-minuta --caso solicitacao_padrao --versao 1 --operador "operador" --decisao aprovar --justificativa "Dados conferidos"
python -m src.main voz --caso solicitacao_padrao --versao 1 --confirmar
python -m src.main imagem --caso solicitacao_padrao
```

### Desafio 2 — NLP, RAG, Guardrails e Sentimentos (`src/desafio2_cli.py`)

```bash
python -m src.desafio2_cli demonstrar-schema
python -m src.desafio2_cli indexar --estrategia structural
python -m src.desafio2_cli listar
python -m src.desafio2_cli avaliar-recuperacao
python -m src.desafio2_cli avaliar-cenarios-rag
python -m src.desafio2_cli compreender --arquivo dados/originais/solicitacoes/SOL-001_audio_desafio1.txt --id SOL-001
python -m src.desafio2_cli avaliar-solicitacoes
python -m src.desafio2_cli consultar --pergunta "Em quais dias e horários funciona o Núcleo Fictício de Atendimento?"
python -m src.desafio2_cli revisar --execution-id ID_DA_EXECUCAO --decisao revisar --justificativa "Conferir fonte." --operador "servidor_atendimento"
python -m src.desafio2_cli revisar-ficha --id SOL-002 --decisao aprovada --justificativa "Dados conferidos." --operador "servidor_atendimento"
python -m src.desafio2_cli avaliar-guardrails
python -m src.desafio2_cli classificar-sentimentos
python -m src.desafio2_cli excluir-documento --documento ACV-ATEND-005 --demonstrar
python -m src.desafio2_cli regressao
python -m src.desafio2_cli avaliar-integrado
```

### Interface Streamlit (`RF20`)

```bash
streamlit run src/app.py
```

### Testes e verificação de entrega

```bash
python -m unittest discover -s testes -v
python scripts/verificar_entrega.py
```

## Resumo dos resultados obtidos

### Desafio 1 (`RF01` a `RF13`)

| Requisito | Resultado |
|---|---|
| `RF01` a `RF05` | Configuração em `config.json`, segredos via `.env`, comparação dos prompts A/B/C com delimitação de entrada não confiável e extração local com geração de minuta rascunho. |
| `RF06` e `RF07` | STT (`gpt-4o-transcribe`) com WER `0,0154` e `2/3` campos críticos (`90/100`). TTS (`gpt-4o-mini-tts`) bloqueado sem aprovação prévia e gerado após aprovação vinculada ao hash SHA-256 (WER de retorno `0,0337`). |
| `RF08` a `RF10` | OCR local via Tesseract com fallback Vision (`70/100`, divergência nos 3 campos críticos retida para confirmação). Peça visual gerada com rótulo sintético e nota de proveniência. |
| `RF11` a `RF13` | Auditoria em `resultados/logs/audit.jsonl` sem chaves nem dados brutos desnecessários, minimização de dados fictícios e avaliação por gabarito. |

### Desafio 2 (`RF14` a `RF24`)

- **Compreensão e schema (`RF14`, `RF15` — `resultados/avaliacao_nlp_desafio2.json`):** validação Pydantic estrita (`solicitacao.v2`) e regras pós-schema (`T01`, `T02`). Nas 6 solicitações: `6/6` categorias, `19/25` campos literais, `25/25` entidades literais e `6/20` termos literais nos resumos (`SOL-001` mantida em `revisar` por omissão da regra de faltas no resumo; `SOL-005` e `SOL-006` sem minuta automática por falta de dados ou ambiguidade).
- **Guardrails (`RF16` — `resultados/avaliacao_guardrails.json`):** `3/3` ataques adversariais (`ADV-01`, `ADV-02`, `ADV-03`) bloqueados e `4/4` controles de escopo, tamanho, extensão e limite de chamadas (`max_calls_per_run = 5`) validados.
- **Busca vetorial e RAG (`RF17`, `RF18`, `RF19`, `RF21` — `resultados/avaliacoes_recuperacao.json`, `resultados/avaliacao_cenarios_rag.json`):** 6 documentos do manifesto indexados no ChromaDB (`17` chunks em `structural`, `11` em `fixed_400_overlap_80`), ambos com `5/5` hits@3. Nos 8 cenários RAG: `8/8` status corretos (`5` fundamentadas com citações verificadas, `2` abstenções sem chamar geração e `1` conflito entre normas apontado para revisão).
- **Sentimentos (`RF22` — `resultados/avaliacao_sentimentos.json`):** `12/12` avaliações classificadas conforme o gabarito (`3` positivas, `3` negativas, `3` neutras e `3` indeterminadas encaminhadas para revisão), com contagem determinística em Python (`T13`).
- **Exclusão, regressão e matriz integrada (`RF20`, `RF23`, `RF24` — `resultados/matriz_testes_rf23.json`):** exclusão de `ACV-ATEND-005` removeu seus chunks da busca (`2` antes, `0` depois) e invalidou respostas dependentes; `3/3` entradas do Desafio 1 (texto, áudio e OCR) rodaram no fluxo novo; `15/15` testes obrigatórios (`T01` a `T15`) e `170` testes unitários aprovados.
