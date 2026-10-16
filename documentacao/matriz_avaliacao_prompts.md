# Avaliação dos prompts A, B e C

## Protocolo e evidência

- Caso: `arquivos/entrada_texto.txt`; gabarito definido antes desta execução em `dados/gabaritos/entrada_texto.json`.
- Execução real após instalação limpa: `resultados/avaliacao_prompts.json`, identificador `59db8502-f564-4dd4-8bb8-690fb4168923`.
- Provedor/modelo: OpenAI, `gpt-4o-mini`; temperatura `0`; limite de saída `1500`; timeout `30 s`.
- A entrada enviada foi minimizada; o JSON contém prompts, respostas, uso, latência, saída do metaprompt C e validação contra esquema/gabarito.
- C mede o tempo total até o resultado utilizável, somando a chamada do metaprompt à chamada da tarefa.

O protocolo atribui notas de 1 a 5 (5 = melhor desempenho). Formato e critérios de segurança são pontuados com base na execução e nos testes automatizados; fidelidade, completude, tom e utilidade são avaliação técnica do artefato e ainda exigem confirmação da equipe.

| Critério | Prompt A | Prompt B | Prompt C |
|---|---:|---:|---:|
| Fidelidade ao contexto | 5 | 5 | 5 |
| Ausência de dados inventados | 5 | 5 | 5 |
| Completude frente ao gabarito | 4 | 5 | 5 |
| Formato/esquema JSON | 5 | 5 | 5 |
| Tom institucional | 4 | 5 | 4 |
| Sinalização de lacunas | 4 | 5 | 5 |
| Segurança e revisão humana | 4 | 4 | 4 |
| Utilidade para revisão humana | 3 | 5 | 4 |
| Tempo até resultado utilizável | 3,145 s | 2,730 s | 5,589 s |
| Conformidade automática com esquema e gabarito | falhou | passou | falhou |
| Tokens totais reportados | 997 | 1.099 | 1.507 |

## Gravidade e ação

- A: erro moderado; a minuta não usou literalmente “não localizado”, embora os demais campos passassem. Ação: corrigir o prompt e repetir antes de uso.
- B: nenhum erro identificado pelo validador do esquema e pelo gabarito nesta execução. Ação: candidato à revisão humana, não aprovado automaticamente.
- C: nenhum erro identificado no esquema ou gabarito; a confiança retornada foi `0`, portanto a saída requer revisão humana cuidadosa.

Critério operacional: falha de JSON, categoria inválida, dado crítico divergente ou afirmação inventada é erro alto e exige rejeição/nova geração. Omissão de campo ou descumprimento literal do gabarito é erro moderado e também exige correção antes de aprovação. Ajustes apenas de estilo são baixos e podem ser feitos manualmente.

## Resultado e decisão

Os três prompts foram aplicados à mesma solicitação minimizada, com o mesmo modelo e parâmetros. Os três retornaram JSON válido e categoria correta. B e C preservaram os detalhes do curso, marcaram revisão humana, referenciaram a fonte e passaram no gabarito. A não usou literalmente `não localizado` na minuta. B foi o mais rápido entre os aprovados; C também passou, mas retornou confiança `0` e levou mais tempo por incluir a etapa de metaprompt.

A taxa de conformidade automática desta rodada foi 2/3 (66,7%); a taxa de aprovação humana registrada é 0/3, pois nenhuma decisão humana foi inserida ainda. B é o candidato selecionado por combinar conformidade integral e menor latência, ainda sujeito à aprovação humana; as três decisões humanas permanecem pendentes. O operador pode aprovar, rejeitar ou solicitar nova geração pelo comando `revisar` descrito no README. Os resultados correspondem a uma execução por prompt; não representam uma avaliação estatística de estabilidade. O custo monetário não foi estimado porque o projeto não fixa uma tabela de preços vigente.
