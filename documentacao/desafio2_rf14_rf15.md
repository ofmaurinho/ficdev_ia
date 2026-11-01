# Desafio 2 — Schemas e Compreensão de Solicitações (`RF14` e `RF15`)

## 1. Schema e regras de negócio (`src/schemas.py`)

`FichaSolicitacao` (`solicitacao.v2`) usa Pydantic estrito (`extra="forbid"`) para validar protocolo, data, solicitante, assunto, pedido, categoria fechada, resumo, entidades literais, inferências, campos ausentes e estado de revisão.

Após o parse, `validar_ficha()` aplica as regras de negócio:
- a data precisa ser válida no calendário e constar no texto;
- protocolo, solicitante e entidades literais precisam aparecer no texto original;
- campos nulos devem estar listados em `campos_ausentes`;
- o resumo tem limite de 100 palavras;
- a minuta é bloqueada quando faltam campos críticos ou quando a categoria é `revisao` (pedido ambíguo).

O comando `python -m src.desafio2_cli demonstrar-schema` testa três JSONs sintaticamente válidos que falham no schema (`extra_forbidden`, `string_type` e `missing`).

## 2. Compreensão e avaliação (`src/nlp.py`)

As 6 solicitações de `dados/originais/solicitacoes/` foram processadas com `gpt-4o-mini` e comparadas ao gabarito `dados/gabaritos/desafio2_solicitacoes.json` (`resultados/avaliacao_nlp_desafio2.json`):
- **Categorias:** `6/6` corretas.
- **Campos literais:** `19/25`.
- **Entidades literais:** `25/25`.
- **Correspondência lexical nos resumos:** `6/20` (a métrica compara subcadeias exatas e não reconhece paráfrases).
- **Revisão humana:** `SOL-002` foi aprovada (`aprovada`), `SOL-001` ficou em `revisar` (resumo omitiu regra de faltas) e `SOL-005` foi rejeitada (`rejeitada`) por falta de identificação, data e protocolo.
