# Registro de Uso de IA no Desenvolvimento

## 1. Ferramentas utilizadas

- **Assistente de código:** assistente de IA integrado à IDE para apoio na estruturação de módulos Python, testes unitários e revisão dos requisitos do enunciado.
- **API de execução do protótipo:** OpenAI SDK (`gpt-4o-mini`, `text-embedding-3-small`, `gpt-4o-transcribe`, `gpt-4o-mini-tts` e `gpt-image-2.5-flare`), acionada pelos módulos de serviço da aplicação com dados fictícios.

## 2. Principais tarefas apoiadas pelo assistente

1. Implementação inicial e evolução dos módulos multimodais do Desafio 1 (`src/main.py`, `src/audio.py`, `src/vision.py`, `src/image_generation.py`, `src/review.py`).
2. Modelagem dos schemas Pydantic (`src/schemas.py`) e do serviço de compreensão de solicitações (`src/nlp.py`).
3. Implementação da ingestão por manifesto (`src/ingestion.py`), índice ChromaDB (`src/vector_store.py`) e consulta RAG com citações (`src/rag.py`).
4. Implementação dos guardrails em camadas (`src/guardrails.py`), análise de sentimentos com agregação em código (`src/sentiment.py`), interface Streamlit (`src/app.py`) e matriz de verificação `T01`–`T15` (`src/metrics.py`).
5. Escrita de testes automatizados (`testes/`, `170` testes) com clientes simulados para validação sem custo de rede.

## 3. O que foi aceito, ajustado e rejeitado pela equipe

- **Aceito:** separação entre camada de serviço e interface (CLI/Streamlit); validação pós-schema em Python; persistência local no ChromaDB; abstenção antes da geração quando a similaridade fica abaixo de `0.40`; agregação determinística de sentimentos em Python.
- **Ajustado após testes:** inclusão da categoria `revisao` na lista permitida de `src/text_processing.py`; bloqueio de minuta automática quando a solicitação é ambígua (`SOL-006`) ou incompleta (`SOL-005`); normalização de entidades literais para cursos e turnos; restauração de coleções e snapshots na demonstração de exclusão (`RF24`); isolamento de diretórios temporários do Chroma nos testes unitários.
- **Rejeitado:** aprovar automaticamente respostas geradas pelo modelo sem revisão humana; indexar PDFs reais de editais que não fazem parte do acervo fictício; calcular percentuais de sentimento via prompt em vez de código Python; gravar chave de API ou dados brutos desnecessários em logs.

## 4. Validação realizada

- **Testes automatizados:** `170` testes passando via `python -m unittest discover -s testes -v`.
- **Execução de ponta a ponta com API real:** indexação das duas estratégias (`structural` com 17 chunks e `fixed_400_overlap_80` com 11 chunks, ambas com `5/5` hits@3), processamento das 6 solicitações (`6/6` categorias, `19/25` campos literais, `25/25` entidades), execução e revisão humana dos 8 cenários RAG (`resultados/avaliacao_cenarios_rag.json`), contenção dos 3 casos adversariais (`resultados/avaliacao_guardrails.json`), classificação das 12 avaliações (`12/12` acertos em `resultados/avaliacao_sentimentos.json`), demonstração de exclusão (`ACV-ATEND-005`), regressão das 3 entradas do Desafio 1 e aprovação integral da matriz `T01`–`T15` (`15/15`).
- **Declaração:** a equipe revisou o código, os gabaritos, as decisões humanas registradas e as limitações declaradas, assumindo responsabilidade pela entrega.
