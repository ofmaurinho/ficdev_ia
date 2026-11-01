# Integração e Requisitos do Desafio 2

Resumo do estado final dos módulos e requisitos `RF14` a `RF24`:

| Requisito | Módulo principal | Resultado verificado |
|---|---|---|
| `RF14` | `src/schemas.py` | Schema `solicitacao.v2` com Pydantic estrito e validação pós-schema (`T01`, `T02`). |
| `RF15` | `src/nlp.py` | `6/6` categorias, `19/25` campos literais e `25/25` entidades literais (`resultados/avaliacao_nlp_desafio2.json`). |
| `RF16` | `src/guardrails.py` | `3/3` ataques adversariais contidos e `4/4` controles de escopo, tamanho e chamadas aprovados (`resultados/avaliacao_guardrails.json`). |
| `RF17` | `src/ingestion.py`, `src/vector_store.py` | 6 documentos do manifesto indexados no ChromaDB (`17` chunks em `structural`, reindexação sem duplicar). |
| `RF18` | `src/rag_evaluation.py` | `5/5` hits@3 em `structural` e `fixed_400_overlap_80` (`resultados/avaliacoes_recuperacao.json`). |
| `RF19` | `src/rag.py` | `8/8` cenários com status correto, citações válidas, abstenção e detecção de conflito (`resultados/avaliacao_cenarios_rag.json`). |
| `RF20` | `src/app.py` | Interface Streamlit em 4 abas com exibição de `"não localizado"` e limpeza de arquivo temporário. |
| `RF21` | `src/providers.py`, `src/audit.py` | Provedor configurável (`openai` / `simulated`), logs sanitizados e tratamento de erros. |
| `RF22` | `src/sentiment.py` | `12/12` avaliações classificadas conforme o gabarito e agregadas deterministicamente em Python (`resultados/avaliacao_sentimentos.json`). |
| `RF23` | `src/metrics.py` | Matriz `T01` a `T15` com `15/15` testes aprovados e `3/3` casos de regressão do Desafio 1 (`resultados/matriz_testes_rf23.json`). |
| `RF24` | `src/vector_store.py`, `src/rag.py` | Exclusão de `ACV-ATEND-005` demonstrada (`resultados/demonstracao_exclusao_rf24.json`) e decisões humanas registradas com operador. |
