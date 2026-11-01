# Relatório de Execução e Validação — Desafio 2

Resumo das verificações executadas sobre os artefatos de `dados/processados/` e `resultados/`:

- **Ambiente e pacotes:** `pip check`, `compileall` e `python -m src.desafio2_cli demonstrar-schema` executados sem erros.
- **Compreensão NLP (`RF14`, `RF15`):** `6/6` categorias, `19/25` campos literais, `25/25` entidades literais e `6/20` correspondências lexicais nos resumos (`resultados/avaliacao_nlp_desafio2.json`).
- **Ingestão e recuperação (`RF17`, `RF18`):** 6 documentos do manifesto indexados no ChromaDB (`17` chunks em `structural`, `11` em `fixed_400_overlap_80`), ambos com `5/5` hits@3 (`resultados/avaliacoes_recuperacao.json`).
- **Cenários RAG (`RF19`):** `8/8` status esperados (`5` fundamentadas, `2` abstenções e `1` conflito de fontes) em `resultados/avaliacao_cenarios_rag.json`, mais consulta combinada com a ficha `SOL-002`.
- **Guardrails e sentimentos (`RF16`, `RF22`):** `3/3` ataques adversariais contidos (`resultados/avaliacao_guardrails.json`) e `12/12` avaliações classificadas conforme o gabarito (`resultados/avaliacao_sentimentos.json`).
- **Exclusão, regressão e testes (`RF23`, `RF24`):** exclusão de `ACV-ATEND-005` demonstrada (`2` chunks antes, `0` depois), `3/3` entradas do Desafio 1 reexecutadas, `15/15` itens da matriz `T01`–`T15` aprovados e `170` testes unitários passando.
