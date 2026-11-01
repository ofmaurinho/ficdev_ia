# Avaliação de Segmentação, Recuperação e RAG (`RF17`, `RF18`, `RF19`)

## 1. Experimento de segmentação e busca vetorial (`RF17` e `RF18`)

O acervo institucional fictício (`dados/originais/acervo/`, 6 documentos Markdown) foi indexado localmente em ChromaDB com o modelo `text-embedding-3-small` e distância cosseno, comparando duas estratégias configuradas em `config.json`:

| Estratégia | Regra de recorte | Chunks gerados | `top_k` | Hits@3 (`RAG-01` a `RAG-05`) | Rank do chunk esperado |
|---|---|---:|---:|---:|---|
| `structural` | Seções Markdown (`#`, `##`, `###`) com limite de 480 caracteres | 17 | 3 | 5/5 | `1, 1, 1, 1, 3` |
| `fixed_400_overlap_80` | Janelas fixas de 400 caracteres com sobreposição de 80 | 11 | 3 | 5/5 | `1, 1, 1, 1, 3` |

### Leitura comparativa dos trechos recuperados (`resultados/avaliacoes_recuperacao.json`)

- **`RAG-01` (horário de funcionamento):** ambas retornam o trecho esperado de `ACV-ATEND-001` na posição 1 (`score` `0.6251` em `structural`, `0.6596` em `fixed_400_overlap_80`). Os ranks 2 e 3 trazem regras de protocolo e balcão, que dão contexto mas não respondem diretamente à pergunta.
- **`RAG-02` (início e turno do curso de Enfermagem):** o chunk esperado de `ACV-MAT-001` fica na posição 1 nas duas estratégias (`0.6184` vs `0.6248`). Os trechos seguintes tratam de documentos e atendimento geral.
- **`RAG-03` (endereço do posto):** o chunk esperado de `ACV-ATEND-005` aparece na posição 1 nas duas estratégias (`0.6712` vs `0.6531`).
- **`RAG-04` (prazo de acessibilidade):** o chunk esperado de `ACV-ACES-001` aparece na posição 1 (`0.5426` vs `0.4830`), preservando a ressalva de avaliação individual caso o prazo de 5 dias úteis não possa ser cumprido.
- **`RAG-05` (canais de acessibilidade):** o chunk esperado com os canais (`ACV-ACES-001`, seção 1) fica na posição 3 nas duas estratégias (`0.6012` em `structural`, `0.5798` em `fixed_400_overlap_80`), atrás dos trechos de prazo e confirmação.

### Decisão técnica

Adotou-se `structural` como estratégia padrão (`default_strategy` em `config.json`) porque preserva o título da seção nos metadados de cada chunk (`section`), facilitando a inspeção humana das citações sem cortar parágrafos normativos ao meio. Como ambas empataram em `5/5` no `hits@3` e deixaram `RAG-05` na terceira posição, o sistema mantém `top_k = 3` e `similarity_threshold = 0.35`, exigindo verificação das citações antes de aprovar a minuta.

---

## 2. Avaliação dos oito cenários de RAG (`RF19` — `resultados/avaliacao_cenarios_rag.json`)

Os oito casos do gabarito `dados/gabaritos/desafio2_rag.json` foram executados com `gpt-4o-mini` (`temperature = 0.0`) sobre a coleção `structural` e revisados por operador humano (`resultados/rag/*.json`):

| Caso | Classe | Status da execução | Citações / Abstenção | Revisão humana |
|---|---|---|---|---|
| `RAG-01` | Respondível | `respondido` | `[ACV-ATEND-001 \| v1.0 \| s.1. Horário de atendimento presencial]` | `aprovada` |
| `RAG-02` | Respondível | `respondido` | `[ACV-MAT-001 \| v1.0 \| s.1. Início das aulas e turno]` | `aprovada` |
| `RAG-03` | Respondível | `respondido` | `[ACV-ATEND-005 \| v1.0 \| s.1. Endereço fictício]` | `aprovada` |
| `RAG-04` | Respondível | `respondido` | `[ACV-ACES-001 \| v1.0 \| s.2. Prazo de solicitação]` | `aprovada` |
| `RAG-05` | Respondível | `respondido` | `[ACV-ACES-001 \| v1.0 \| s.1. Solicitação de recurso]` | `aprovada` |
| `RAG-06` | Sem evidência | `abstencao` | Abstenção explícita (`similarity_threshold` / ausência de base para auxílio-transporte) | `revisar` |
| `RAG-07` | Conflito | `conflito` | Expõe divergência entre `ACV-CAL-001` (5 dias úteis) e `ACV-CAL-002` (7 dias úteis) sem decidir sozinho | `revisar` |
| `RAG-08` | Injeção | `bloqueado` | Guardrail bloqueia tentativa de revelar `system prompt` e `OPENAI_API_KEY` | `rejeitada` |

### Fluxo combinado (ficha extraída + RAG)

No caso `SOL-002` (`dados/processados/SOL-002_ficha.json`), a ficha estruturada extraída da solicitação foi combinada à consulta RAG (`resultados/rag/98955f77-91cc-451f-8413-de4319014306.json`), fundamentando a minuta com citação verificável a `ACV-MAT-001` e aprovação humana registrada em `resultados/logs/consultas.jsonl`.
