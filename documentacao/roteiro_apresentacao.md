# Roteiro de Apresentação — 12 minutos

**Central Inteligente de Atendimento e Comunicação Institucional (Desafios 1 e 2)**

> Tempo total: 12 min.

## Bloco 1 — Problema, arquitetura e schema (2 min)

- Contexto: triagem de solicitações em texto, áudio e PDF/imagem, fundamentação no acervo fictício e revisão humana obrigatória antes de qualquer resposta.
- Diferença entre JSON válido, conformidade ao schema Pydantic (`solicitacao.v2`) e regra de negócio pós-schema:
```bash
python -m src.desafio2_cli demonstrar-schema
```

## Bloco 2 — Compreensão de solicitações, busca vetorial e RAG (4 min)

- Processamento das solicitações (`SOL-001` a `SOL-006`) e entradas herdadas do Desafio 1 (texto, áudio STT e OCR):
```bash
python -m src.desafio2_cli avaliar-solicitacoes
python -m src.desafio2_cli regressao
```
- Mostrar uma ficha completa (`SOL-002_ficha.json`, aprovada) e uma incompleta/ambígua (`SOL-005_ficha.json` / `SOL-006_ficha.json`, com minuta bloqueada).
- Comparação de segmentação (`structural` vs. `fixed_400_overlap_80`, `5/5` hits@3) e execução dos 8 cenários RAG (citações, abstenção em `RAG-06`/`RAG-07` e conflito em `RAG-08`):
```bash
python -m src.desafio2_cli listar
python -m src.desafio2_cli avaliar-cenarios-rag
```

## Bloco 3 — Guardrails, sentimentos, exclusão e Streamlit (4 min)

- Contenção de prompt injection e controle de escopo/recursos (`ADV-01` a `ADV-03`):
```bash
python -m src.desafio2_cli avaliar-guardrails
```
- Classificação individual das 12 avaliações fictícias (`12/12`) e agregação determinística em Python:
```bash
python -m src.desafio2_cli classificar-sentimentos
```
- Demonstração de exclusão lógica de `ACV-ATEND-005` e invalidação de respostas derivadas:
```bash
python -m src.desafio2_cli excluir-documento --documento ACV-ATEND-005 --demonstrar
```
- Navegação rápida pelas 4 abas da interface local:
```bash
streamlit run src/app.py
```

## Bloco 4 — Auditoria, matriz integrada e limitações (2 min)

- Conferência da matriz `T01` a `T15` (`15/15` aprovados) e dos logs sanitizados (`resultados/logs/audit.jsonl` e `resultados/logs/consultas.jsonl`):
```bash
python -m src.desafio2_cli avaliar-integrado
python scripts/verificar_entrega.py
```
- Limitações: amostra reduzida de avaliação, limiar `0.40` ajustado para o acervo sintético, confiança não calibrada do classificador e ausência de cálculo monetário automático.
