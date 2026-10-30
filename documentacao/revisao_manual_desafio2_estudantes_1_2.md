# Revisão manual — Desafio 2 (Estudantes 1 e 2)

Este guia indica o que conferir antes de considerar RF14/RF15 e RF17/RF18/RF19/RF21 finalizados. A execução técnica já ocorreu, mas os relatórios mostram divergências de extração e não aprovam semanticamente fichas nem respostas.

## Arquivos para consultar

| Conteúdo | Caminho |
|---|---|
| Solicitações de origem | `dados/originais/solicitacoes/SOL-001_*.txt` a `SOL-006_*.txt` |
| Gabarito manual das fichas | `dados/gabaritos/desafio2_solicitacoes.json` |
| Fichas geradas pelo prompt v2 | `dados/processados/SOL-001_ficha.json` a `SOL-006_ficha.json` |
| Comparação agregada das fichas | `resultados/avaliacao_nlp_desafio2.json` |
| Gabarito das oito perguntas RAG | `dados/gabaritos/desafio2_rag.json` |
| Resultado dos cenários RAG | `resultados/avaliacao_cenarios_rag.json` |
| Detalhes de cada consulta e citações | `resultados/rag/<execution_id>.json` — use o `execution_id` em cada linha do relatório RAG |
| Trechos recuperados por estratégia | `resultados/avaliacoes_recuperacao.json` |
| Fontes institucionais fictícias | Arquivos listados em `dados/originais/acervo/manifest.json` |

As rodadas anteriores da avaliação de fichas foram preservadas em `resultados/avaliacao_nlp_desafio2_rodada_1.json` e `resultados/avaliacao_nlp_desafio2_rodada_2.json`. O relatório atual usa `compreensao_solicitacao.v2`; o RAG atual usa `rag_institucional.v2`.

## RF14/RF15 — conferir as seis fichas

Para cada solicitação, compare o TXT original, o gabarito e o JSON gerado. No JSON, confira `ficha`, `alertas_negocio`, `status`, `minuta` e `metadata.normalizacoes_negocio`. As normalizações mantêm os campos críticos nulos coerentes com `campos_ausentes` e tornam a revisão humana obrigatória; confirme que não esconderam uma lacuna real.

| Caso | Conferência principal |
|---|---|
| SOL-001 | A data gerada é “14 de outubro de 2026”, enquanto o gabarito usa “14/10/2026”: confirme que são a mesma data do pedido, não a data de nascimento. O assunto gerado (“efetivação da matrícula”) é mais amplo/diferente do gabarito (“matrícula em curso técnico”). Veja se o resumo conserva curso, turno noturno, 1.200 horas, documentos pedidos e a regra de faltas. |
| SOL-002 | O assunto gerado é apenas “Matrícula”. Decida se é suficientemente específico para representar matrícula no curso Técnico em Administração. Confira se o resumo preserva que o formulário já foi entregue e que se pede o próximo passo. A lista de entidades não contém protocolo, data nem solicitante, apesar de esses campos estarem preenchidos na ficha. |
| SOL-003 | Compare “data e turno de curso” do gabarito com o assunto mais longo gerado. Verifique se o resumo explicita que a pessoa pergunta tanto a data de início quanto o turno. A lista de entidades saiu vazia, embora protocolo, data, solicitante e curso estejam presentes no pedido/ficha. |
| SOL-004 | Há divergência de categoria: gabarito `solicitacao_servico`, saída `informacao`. Leia a frase de intenção no original e decida qual rótulo se aplica. Confira se “Acessibilidade” é assunto suficientemente específico e se o resumo não infere condição de saúde; o pedido diz que não informa diagnóstico. |
| SOL-005 | Confirme que protocolo, data e solicitante permanecem nulos e aparecem em `campos_ausentes`; a minuta deve estar bloqueada (`minuta: null`). Veja se o assunto/resumo descreve apenas o pedido de informações sobre matrícula, sem inventar identificadores. |
| SOL-006 | Há divergência de categoria: gabarito `revisao`, saída `solicitacao_servico`. O pedido “Resolva isso” não identifica quais documentos divergem nem qual providência é possível. Confirme se deve permanecer ambíguo e sem minuta (`assunto: null`, campo ausente). |

No relatório agregado, as medidas atuais são **4/6 categorias**, **19/24 campos literais**, **6/20 fatos com correspondência lexical no resumo** e **10/25 entidades esperadas recuperadas literalmente**. A comparação literal pode penalizar uma formulação semanticamente equivalente (por exemplo, datas por extenso); ela não substitui sua decisão. Registre separadamente: correspondência literal, equivalência semântica, fato omitido, fato acrescentado e decisão.

### Registro de decisão por ficha

Preencha após comparar fonte, gabarito e saída. Se corrigir um gabarito, registre a justificativa e a evidência no TXT de origem antes de recalcular métricas.

| Caso | Categoria aceita? | Campos aceitos/corrigidos | Resumo fiel? | Entidades completas? | Minuta pode permanecer? | Revisor/data/observação |
|---|---|---|---|---|---|---|
| SOL-001 |  |  |  |  |  |  |
| SOL-002 |  |  |  |  |  |  |
| SOL-003 |  |  |  |  |  |  |
| SOL-004 |  |  |  |  |  |  |
| SOL-005 |  |  |  |  |  |  |
| SOL-006 |  |  |  |  |  |  |

## RF17 — índice e ingestão

O índice atual está em `dados/indice/chroma`; `python -m src.desafio2_cli listar` deve mostrar os seis IDs do manifesto e 17 chunks no total para a coleção estrutural. O relatório de indexação mostrou substituição dos chunks anteriores na segunda indexação, sem duplicação.

Antes de aceitar RF17, confira ainda:

- Reinicie o processo Python e liste o índice novamente; confirme persistência e os mesmos seis documentos.
- Confirme que o manifesto é a única fonte de ingestão e que nenhum PDF de aula, desafio ou edital em `arquivos/` aparece no índice.
- Para PDFs do acervo, confirme que número de página/seção exibido vem dos metadados da extração, não de texto gerado pelo modelo.
- O acervo contém PDFs textuais. PDF sem camada de texto/OCR e rejeição de caminho fora do diretório autorizado ainda precisam de uma demonstração isolada, sem inserir o arquivo de teste no manifesto institucional.

## RF18 — chunking e busca

Abra `resultados/avaliacoes_recuperacao.json` e confira, para cada uma das cinco perguntas respondíveis, `expected_chunk_ids`, `returned_chunk_ids`, `hit` e os textos em `retrieved`. As duas estratégias tiveram **5/5 hits@3**. O empate não prova que os trechos têm contexto igualmente útil.

| Estratégia | Perguntas corretas | O que revisar nos trechos |
|---|---:|---|
| `structural` | 5/5 | Seção/parágrafo recuperado contém resposta completa ou perdeu ressalva em outra unidade? |
| `fixed_400_overlap_80` | 5/5 | O corte de 400 caracteres preserva contexto suficiente? A sobreposição de 80 duplica informação sem trazer benefício? |

Revise os dez resultados recuperados (cinco por estratégia), marque se o trecho contém a resposta inteira e registre qual estratégia preserva melhor o contexto. Não selecione pela contagem de hits sozinha.

## RF19 — respostas, abstenção e citações

No `resultados/avaliacao_cenarios_rag.json`, localize cada `execution_id` e abra o JSON correspondente em `resultados/rag/`. Compare `answer`, `status`, `sources`, `citations` e `abstention_reason` com os fatos e as referências do gabarito.

| ID | Status esperado/obtido | O que verificar semanticamente |
|---|---|---|
| RAG-01 | `fundamentada` / `fundamentada` | Dias, horário e exceção de feriados; confirme que a citação vem da seção de horário. |
| RAG-02 | `fundamentada` / `fundamentada` | Tradução do PDF em inglês: data 2027-02-01 e turno noturno; conferir página 1 e chunk citado. |
| RAG-03 | `fundamentada` / `fundamentada` | Endereço completo: Rua das Acacias, 120, Centro, Serra Clara. |
| RAG-04 | `fundamentada` / `fundamentada` | A resposta atual menciona cinco dias úteis, mas o gabarito também exige a alternativa: se não cumprir o prazo, registrar para avaliação individual. Verifique se essa ressalva deve ser incluída. |
| RAG-05 | `fundamentada` / `fundamentada` | A resposta atual menciona canal da unidade e e-mail. O gabarito também cita balcão principal e encaminhamento à coordenação; confira se as fontes citadas sustentam esses detalhes e se a resposta deve incluí-los. |
| RAG-06 | `sem_evidencia` / `sem_evidencia` | Não há valor de bolsa no acervo; confirme abstenção e ausência de geração. |
| RAG-07 | `sem_evidencia` / `sem_evidencia` | Não há cardápio no acervo; confirme abstenção e ausência de geração. |
| RAG-08 | `conflito_de_fontes` / `conflito_de_fontes` | As orientações de matrícula discordam e têm a mesma prioridade. Confirme que nenhuma foi escolhida ou apresentada como regra. |

Nas cinco respostas fundamentadas, revise **cada** objeto em `citations`: a afirmação deve estar apoiada pelo texto literal daquele `chunk_id`. A checagem automática confirma que o ID foi recuperado, não que a afirmação é verdadeira ou que a citação é suficiente. Registre se faltou ressalva, se houve tradução incorreta ou se há afirmação sem suporte.

### Registro de decisão por consulta

| ID | Status correto? | Todas as afirmações apoiadas? | Citações suficientes? | Ressalvas preservadas? | Decisão humana/justificativa/data |
|---|---|---|---|---|---|
| RAG-01 |  |  |  |  |  |
| RAG-02 |  |  |  |  |  |
| RAG-03 |  |  |  |  |  |
| RAG-04 |  |  |  |  |  |
| RAG-05 |  |  |  |  |  |
| RAG-06 |  |  |  |  |  |
| RAG-07 |  |  |  |  |  |
| RAG-08 |  |  |  |  |  |

O limiar `0.40` separou estes oito casos sintéticos: as consultas respondíveis tiveram similaridade máxima de pelo menos `0.444`, e as duas consultas sem resposta ficaram em até `0.334`. Essa amostra é pequena. Antes de generalizar o limiar, inclua consultas variadas, paráfrases, perguntas ambíguas e negativas próximas ao tema do acervo; registre falsos positivos e falsos negativos.

## RF21 — provedor, auditoria e falhas

Já foram exercitados OpenAI Responses/embeddings, o modo `simulated` e a falha de índice vazio. Antes de fechar RF21, confira:

- Os resultados RAG registram modelo, versão de prompt, duração, uso informado pelo SDK, fontes e decisão pendente; os logs não devem conter chave nem texto bruto desnecessário.
- `simulated` deve continuar claramente identificado e nunca ser contado como resposta real.
- O custo monetário não está calculado. Se o requisito da entrega pedir custo, use uma fonte de preços vigente, registre a data e deixe explícitos os tokens usados.
- Falhas de autenticação, limite e timeout ainda podem ser verificadas em ambiente controlado, sem colocar credenciais inválidas em arquivos ou logs. Confirme que a mensagem exibida é sanitizada e que a execução termina em revisão humana.
- A configuração atual usa OpenAI; não houve benchmark de latência/custo entre provedores.

## Condições para marcar o escopo dos Estudantes 1 e 2 como revisado

- [ ] Revisar as seis fichas e preencher a tabela de decisões, incluindo categoria, campos, resumo e entidades.
- [ ] Resolver as divergências SOL-001, SOL-004 e SOL-006 e registrar se a saída ou o gabarito precisava de correção.
- [ ] Conferir as cinco respostas fundamentadas frase por frase e tratar as ressalvas indicadas em RAG-04/RAG-05.
- [ ] Conferir abstenções, conflito e citações; registrar decisão humana sem aprovação automática.
- [ ] Validar persistência após reinício e documentar PDF sem camada de texto e bloqueio de caminhos fora do acervo.
- [ ] Revisar as duas estratégias pelo conteúdo recuperado e documentar a escolha ou manter empate justificado.
- [ ] Reavaliar o limiar com perguntas novas; não tratá-lo como calibrado para uso geral.
- [ ] Atualizar os resultados/documentação com decisões, revisor e data. Só então declarar o escopo revisado; RF16, RF20 e RF22 continuam pertencendo ao Estudante 3.

## Adendo de estado — 30/10/2026

A implementação vigente usa prompt `compreensao_solicitacao.v3`, schema/gabarito `solicitacao.v2` e prompt RAG `rag_institucional.v2`. Este roteiro foi elaborado para saídas anteriores. As métricas nele reproduzidas e os JSONs em `resultados/` são históricos e não devem ser lidos como validação do novo gabarito. Entradas originais e resultados anteriores foram preservados; não houve nova chamada paga nem regravação das fichas durante a correção. Para validar a versão atual, gere um novo artefato em uma nova rodada explicitamente identificada.

As correções estruturais, tipagem de entidades e privacidade são cobertas por `testes/test_desafio2_correcoes.py` (11 testes com mocks). A revisão semântica das seis fichas e das respostas RAG ainda exige comparação humana antes de marcar os requisitos como aprovados. Para RF18, consulte `analise_rf18_relevancia.md`: há ruído entre os top-3 e nenhuma estratégia foi escolhida vencedora.

## Atualização após a reexecução de 30/10/2026

A rodada atual tem gabarito v2 com acentuação reparada e fichas v3/v2 reavaliadas localmente. Entidades alcançaram 25/25 após correção local de nome de curso, turno e eixo tecnológico. Isso não encerra a revisão semântica: SOL-001 ainda omite a regra de cancelamento por faltas no resumo. Para RAG, os oito estados batem e as cinco citações fundamentadas apontam para chunks recuperados; RAG-05 omite o encaminhamento à coordenação, e RAG-01 tem citação acessória a revisar. Consulte `documentacao/relatorio_reexecucao_desafio2_2026-10-30.md` para as evidências e mantenha as decisões humanas pendentes até conferência.
