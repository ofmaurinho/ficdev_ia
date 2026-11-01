# Revisão das Fichas e Consultas RAG (`RF14`, `RF15` e `RF19`)

Registro consolidado da revisão humana sobre as 6 fichas extraídas (`dados/processados/SOL-001_ficha.json` a `SOL-006_ficha.json`) e as 8 consultas do gabarito RAG (`resultados/avaliacao_cenarios_rag.json`).

## 1. Revisão das fichas de solicitação

| Caso | Categoria | Minuta gerada | Decisão humana | Observação |
|---|---|---|---|---|
| `SOL-001` | `solicitacao_servico` | Sim | `revisar` | Data por extenso equivale a `14/10/2026`, mas o resumo omitiu a regra de cancelamento por faltas nos primeiros dias. |
| `SOL-002` | `solicitacao_servico` | Sim | `aprovada` | Protocolo, data, solicitante e curso conferem com o original. |
| `SOL-003` | `informacao` | Sim | `revisar` | Dúvida sobre data de início e turno extraída corretamente; aguardando conferência final. |
| `SOL-004` | `solicitacao_servico` | Sim | `revisar` | Pedido de recurso de acessibilidade sem inferir diagnóstico de saúde. |
| `SOL-005` | `informacao` | Não (`null`) | `rejeitada` | Solicitação sem protocolo, data e nome; minuta bloqueada pela regra de negócio. |
| `SOL-006` | `revisao` | Não (`null`) | `revisar` | Pedido ambíguo ("Resolva isso") sem especificar documentos divergentes; minuta bloqueada. |

## 2. Revisão dos cenários RAG

| Caso | Status | Decisão humana | Observação |
|---|---|---|---|
| `RAG-01` | `fundamentada` | `revisar` | Horário e dias corretos (`ACV-ATEND-001`), com segunda citação acessória sobre protocolo. |
| `RAG-02` | `fundamentada` | `aprovada` | Início `2027-02-01` e turno noturno corretos (`ACV-MATR-004`, p. 1). |
| `RAG-03` | `fundamentada` | `aprovada` | Endereço completo (`ACV-ATEND-005`, p. 1). |
| `RAG-04` | `fundamentada` | `aprovada` | Prazo de 5 dias úteis e alternativa de avaliação individual (`ACV-ACESS-003`). |
| `RAG-05` | `fundamentada` | `rejeitada` | Cita os canais de atendimento, mas omite o encaminhamento à coordenação responsável. |
| `RAG-06` | `sem_evidencia` | `revisar` | Abstenção correta (auxílio/bolsa ausente no acervo). |
| `RAG-07` | `sem_evidencia` | `revisar` | Abstenção correta (cardápio ausente no acervo). |
| `RAG-08` | `conflito_de_fontes` | `revisar` | Divergência entre `ACV-MATR-002` e `ACV-MATR-006` sinalizada sem escolher uma regra. |
