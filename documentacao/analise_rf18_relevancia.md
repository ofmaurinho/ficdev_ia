# RF18 — análise offline da relevância recuperada

## Evidência usada

Esta análise lê o relatório histórico `resultados/avaliacoes_recuperacao.json`, medido em 30/10/2026. Não executa embeddings, não altera o relatório e não escolhe uma estratégia automaticamente.

| Estratégia | Unidades no índice | Hits@3 | Posição do chunk esperado (RAG-01 a RAG-05) |
|---|---:|---:|---|
| `structural` | 17 | 5/5 | 1, 1, 1, 1, 3 |
| `fixed_400_overlap_80` | 11 | 5/5 | 1, 1, 1, 1, 3 |

O resultado mede se ao menos um chunk de referência aparece entre os três primeiros. Não mede sozinho se todos os trechos são relevantes, se a resposta completa está no chunk nem se uma resposta gerada preserva ressalvas.

## Leitura dos resultados

- **RAG-01 — horário:** as duas estratégias retornam o horário esperado em primeiro lugar. Em seguida aparece o chunk de atendimento por protocolo; o terceiro resultado structural não tem seção identificada, enquanto o terceiro fixed é o balcão principal. Esses itens podem ser contexto útil do atendimento, mas não respondem ao horário.
- **RAG-02 — início e turno do curso:** ambas colocam o chunk esperado primeiro. Depois recuperam trechos de identificação/documentos e horário de atendimento, que não respondem à pergunta.
- **RAG-03 — endereço:** ambas colocam o endereço esperado primeiro. Horário de atendimento e acessibilidade aparecem depois e são irrelevantes para o endereço.
- **RAG-04 — prazo de acessibilidade:** ambas colocam primeiro o chunk do prazo e confirmação. O segundo resultado é a solicitação de recurso, potencialmente complementar; o terceiro structural não identifica seção. A revisão da resposta deve confirmar que a alternativa de avaliação individual quando o prazo não puder ser cumprido não foi perdida.
- **RAG-05 — canais de acessibilidade:** o chunk com canais esperados aparece em terceiro nas duas estratégias. Os dois primeiros chunks structural e fixed são relacionados ao pedido/prazo, mas não contêm os canais; avalie se o top-k e o limiar dão prioridade suficiente à evidência diretamente responsiva.

## Conclusão e limite

As duas estratégias empatam em hits@3 e na posição do chunk esperado para estes cinco casos. A estratégia estrutural produz mais unidades (17 contra 11), mas isso não demonstra superioridade. Os resultados apontam ruído nos ranks 2 e 3 de RAG-02/RAG-03 e deixam o chunk de canais de RAG-05 em terceiro. Portanto, mantenha a escolha em aberto até revisão humana dos textos completos e teste adicional com paráfrases, consultas negativas próximas e perguntas que exijam mais de um trecho. Não há alteração do índice persistente nem do benchmark histórico nesta análise.
