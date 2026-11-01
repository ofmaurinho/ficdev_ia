# Avaliação de Segmentação, Recuperação e RAG

## 1. Comparação de segmentação (`RF17` e `RF18`)

O acervo fictício (`dados/originais/acervo/manifest.json`, com 3 arquivos TXT e 3 PDFs) foi indexado no ChromaDB usando `text-embedding-3-small` (1536 dimensões) e distância cosseno. Comparamos duas estratégias com `top_k = 3`:

| Estratégia | Regra | Chunks | Hits@3 (`RAG-01` a `RAG-05`) | Posição do chunk esperado |
|---|---|---:|---:|---|
| `structural` | Por seção e parágrafo | 17 | 5/5 | 1, 1, 1, 1, 3 |
| `fixed_400_overlap_80` | Blocos de 400 caracteres (sobreposição de 80) | 11 | 5/5 | 1, 1, 1, 1, 3 |

### Observações sobre a busca (`resultados/avaliacoes_recuperacao.json`)

- Em `RAG-01` (`ACV-ATEND-001`), `RAG-02` (`ACV-MATR-004`), `RAG-03` (`ACV-ATEND-005`) e `RAG-04` (`ACV-ACESS-003`), o trecho esperado ficou em 1º lugar nas duas estratégias.
- Em `RAG-05` (`ACV-ACESS-003`, canais de acessibilidade), o trecho esperado ficou em 3º lugar nas duas estratégias, atrás dos trechos sobre prazo e confirmação.
- Mantivemos `structural` como padrão em `config.json` porque preserva o título da seção nos metadados e evita cortar parágrafos normativos ao meio.

## 2. Cenários de RAG e revisão humana (`RF19`)

Os 8 casos de `dados/gabaritos/desafio2_rag.json` foram executados com `gpt-4o-mini` (`temperature = 0`) e revisados manualmente (`resultados/avaliacao_cenarios_rag.json`):

| Caso | Esperado | Obtido | Fonte principal | Decisão humana | Observação |
|---|---|---|---|---|---|
| `RAG-01` | `fundamentada` | `fundamentada` | `ACV-ATEND-001` | `revisar` | Cobre horário e dias, mas incluiu citação extra de protocolo. |
| `RAG-02` | `fundamentada` | `fundamentada` | `ACV-MATR-004` (p. 1) | `aprovada` | Data `2027-02-01` e turno noturno corretos a partir do PDF em inglês. |
| `RAG-03` | `fundamentada` | `fundamentada` | `ACV-ATEND-005` (p. 1) | `aprovada` | Endereço completo com citação válida. |
| `RAG-04` | `fundamentada` | `fundamentada` | `ACV-ACESS-003` | `aprovada` | Prazo de 5 dias úteis e ressalva de avaliação individual preservados. |
| `RAG-05` | `fundamentada` | `fundamentada` | `ACV-ACESS-003` | `rejeitada` | Informou os canais, mas omitiu o encaminhamento à coordenação. |
| `RAG-06` | `sem_evidencia` | `sem_evidencia` | — | `revisar` | Abstenção sem chamar o gerador (bolsa/auxílio não consta no acervo). |
| `RAG-07` | `sem_evidencia` | `sem_evidencia` | — | `revisar` | Abstenção sem chamar o gerador (cardápio não consta no acervo). |
| `RAG-08` | `conflito_de_fontes` | `conflito_de_fontes` | `ACV-MATR-002` / `ACV-MATR-006` | `revisar` | Apontou divergência entre as normas de matrícula sem escolher uma sozinho. |

No fluxo combinado (`resultados/rag/98955f77-91cc-451f-8413-de4319014306.json`), a ficha `SOL-002` foi usada junto com a busca no acervo para fundamentar a resposta com citação verificada e revisão aprovada. O limiar `similarity_threshold = 0.40` separou bem esses 8 casos de teste, mas precisa ser recalibrado se o acervo crescer.
