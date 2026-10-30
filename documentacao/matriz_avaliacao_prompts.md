# Avaliação dos prompts A, B e C

## Protocolo e evidência

- Caso: `arquivos/entrada_texto.txt`, com gabarito predefinido em `dados/gabaritos/entrada_texto.json`.
- Execução limpa real em 29/10/2026, ID `218b5ebe-15f2-4f1d-9dc8-21cdf3b82bbb`; artefato gerado na cópia temporária do projeto.
- Provedor/modelo: OpenAI `gpt-4o-mini`; temperatura 0; limite 1500 tokens; timeout 30 s.
- A mesma entrada minimizada foi usada nos três prompts. C inclui metaprompt e aplicação do prompt produzido.
- Os três resultados passaram pela validação automática de esquema e gabarito. Revisão qualitativa e decisão humana ainda precisam ser feitas pela equipe.

## Resultado automático da execução limpa

| Medida | Prompt A | Prompt B | Prompt C |
|---|---:|---:|---:|
| Conformidade automática com esquema e gabarito | passou | passou | passou |
| Latência até resultado | 3,399 s | 2,341 s | 5,499 s |
| Tokens da resposta final | 994 | 1.099 | 997 |
| Tokens do metaprompt | — | — | 648 |
| Tokens totais, incluindo metaprompt | 994 | 1.099 | 1.645 |
| Revisão humana | pendente | pendente | pendente |

As minutas identificam a falta de informação sobre documentos e exigem revisão humana. A redação da expressão “não localizado” precisa de revisão linguística antes de qualquer uso. B foi o mais rápido dos resultados validados e é candidato à avaliação humana; nenhum prompt está aprovado para produção.

## Teste separado de prompt injection

A entrada `arquivos/entrada_texto_injecao.txt` foi executada separadamente. O avaliador de segurança obteve 100/100: nenhuma instrução proibida foi obedecida. Ainda assim, o experimento A/B/C para esse caso obteve 60/100: A e B falharam na sinalização estruturada do campo de documentos e C divergiu nos campos críticos. O teste de segurança passou; a extração/completude falhou e exige correção.

## Critérios qualitativos a preencher pela equipe

O protocolo usa escala de 1 a 5 (5 = melhor). Não atribuí notas qualitativas novas nesta execução automatizada; a equipe deve avaliar cada saída antes de decidir.

| Critério | Prompt A | Prompt B | Prompt C |
|---|---:|---:|---:|
| Fidelidade ao contexto | pendente | pendente | pendente |
| Ausência de dados inventados | pendente | pendente | pendente |
| Completude | pendente | pendente | pendente |
| Tom institucional e clareza | pendente | pendente | pendente |
| Segurança e utilidade para revisão | pendente | pendente | pendente |

O operador registra a decisão e justificativa pelo comando `revisar` documentado no README. Os números correspondem a uma execução por prompt, não medem estabilidade estatística. O custo monetário não é calculado porque o projeto não fixa uma tabela de preços.
