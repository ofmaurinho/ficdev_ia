# Continuidade do Desafio Prático 2 — Estudante 3

## Estado desta etapa

O escopo desta etapa foi RF14/RF15 e RF17/RF18/RF19/RF21, mais contratos/documentação de integração. Em 30/10/2026 houve chamadas reais ao modelo e ao endpoint de embeddings para executar os cenários fictícios; nenhum custo monetário foi calculado. A chave do `.env` não foi exibida nem modificada. Importar os módulos não instancia cliente OpenAI; o carregador `load_dotenv()` existente pode carregar variáveis no processo.

O acervo RAG aceita somente os seis arquivos enumerados em `dados/originais/acervo/manifest.json` (3 TXT, 3 PDFs textuais fictícios). Arquivos de aula, enunciados e editais presentes em `arquivos/` não entram no índice. Há seis solicitações fictícias em `dados/originais/solicitacoes/` e seus gabaritos em `dados/gabaritos/desafio2_solicitacoes.json` (4 completas, 1 incompleta, 1 ambígua). Uma reutiliza a transcrição revisada do Desafio 1. O TXT OCR herdado contém erros/ilegibilidade e pode ser lido como entrada, mas seus campos não foram promovidos a gabarito verdadeiro. Doze avaliações e três casos adversariais estão em arquivos separados em `dados/originais/avaliacoes/`; são dados de referência, não saídas de modelo.

### Módulos e contratos efetivamente disponíveis

- Desafio 1 preservado: `src/main.py`, `src/text_processing.py`, `src/audio.py`, `src/vision.py`, `src/review.py`, `src/audit.py`, `src/llm_client.py` e fluxos de imagem/minuta existentes.
- `src/schemas.py`: `FichaSolicitacao` (`solicitacao.v2`), `RespostaRAG`, cita??es e valida??o de neg?cio; demonstra??o local JSON/schema.
- `src/nlp.py`: `processar_solicitacao()`, `processar_arquivo_solicitacao()`, `carregar_texto_solicitacao()`, `avaliar_ficha()` e `avaliar_conjunto_solicitacoes()`. O serviço pode ler TXT revisado de áudio/OCR do Desafio 1; JSON legado sem o texto integral deve ser acompanhado do TXT correspondente.
- `src/ingestion.py`: `carregar_manifesto()`, `chunk_document()` e `chunk_corpus()`. TXT usa UTF-8; PDF usa `pymupdf.open()` e registra página humana desde a extração; PDF sem camada textual retorna `OCRRequiredError`.
- `src/vector_store.py`: `indexar_acervo()`, `search_chunks()` e `listar_documentos_indexados()`. Usa `chromadb.PersistentClient`, embedding explícito, `get_or_create_collection` e distância cosine. Mudança de modelo/dimensão/estratégia sinaliza índice incompatível.
- `src/rag_evaluation.py`: `avaliar_chunking()` compara as cinco perguntas respondíveis em duas coleções persistentes, com o mesmo embedding/top-k e referências determinísticas de chunk.
- `src/rag.py`: `consultar_rag()` e `registrar_revisao_rag()`. Retorna estados `fundamentada`, `sem_evidencia`, `conflito_de_fontes`, `revisao_humana`, fontes com excerto original e decisão humana pendente. A aprovação só é aceita para status fundamentada; não há envio externo.
- `src/desafio2_cli.py`: camada CLI sem UI. Comandos confirmados: `demonstrar-schema`, `indexar`, `listar`, `avaliar-recuperacao`, `compreender`, `avaliar-solicitacoes`, `consultar` e `revisar`.
- `src/llm_client.py`: foi estendido com `parse_structured()` usando `client.responses.parse()` e `create_embeddings()`; ambos são chamados apenas em funções de serviço após solicitação explícita.

## Situação por requisito

| Requisito | Estado | Evidência/limite atual |
|---|---|---|
| RF14 | Executado; qualidade atual ainda requer valida??o | Schema `solicitacao.v2`, prompt `compreensao_solicitacao.v3`, valida??o de neg?cio e tipagem de entidades. Fichas/relat?rios anteriores s?o hist?ricos e n?o foram recalculados contra o gabarito v2. |
| RF15 | Parcial | Avaliação real dos seis gabaritos: categoria 4/6; campos literais 19/24; fatos no resumo 6/20 por correspondência lexical; entidades 10/25 de revocação literal. Assuntos e resumos exigem revisão semântica humana; três rodadas estão em `resultados/avaliacao_nlp_desafio2.json` e `resultados/avaliacao_nlp_desafio2_rodada_1.json` / `_rodada_2.json`. |
| RF16 | Pendente | Casos adversariais de referência foram criados; guardrails em camadas/moderação não foram implementados. Delimitadores, limite de comprimento e validação do schema são controles básicos, insuficientes como RF16. |
| RF17 | Executado | Seis documentos (3 TXT/3 PDF textual) indexados no Chroma persistente, 17 chunks estruturais, embedding `text-embedding-3-small` 1536D. Reindexação substituiu os chunks existentes sem duplicar: 17 continuaram no índice. |
| RF18 | Executado; estratégia não escolhida | Em `resultados/avaliacoes_recuperacao.json`, structural e fixed 400/80 atingiram 5/5 hits em top-k=3. Empate de recall; contexto ainda deve ser revisto antes de selecionar. |
| RF19 | Executado; revisão humana pendente | Oito consultas reais com `rag_institucional.v2` corresponderam ao status do gabarito (5 fundamentadas, 2 sem evidência, 1 conflito); nenhuma citação inválida. Relatório: `resultados/avaliacao_cenarios_rag.json`. As respostas fundamentadas continuam sem aprovação humana. |
| RF20 | Pendente | Nenhum Streamlit ou painel foi adicionado. |
| RF21 | Parcial | OpenAI Responses/embeddings, configuração por provedor, logs de uso e dry-run `simulated` foram exercitados. A falha com índice vazio foi convertida em revisão humana. Não houve comparação entre provedores nem cálculo monetário de custo. |
| RF22 | Pendente | Os 12 textos e gabaritos foram criados; classificador e painel não foram implementados. |
| RF23 | Pendente | Não foi executada a matriz integrada do Desafio 2; regressão de áudio/OCR segue pendente nesta etapa. Não reportar taxas sem execução real. |
| RF24 | Parcial | Dados fictícios e minimização/logs foram considerados; `registrar_revisao_rag()` fornece ponto de decisão humana. Retenção/exclusão de documentos, chunks e derivados não está implementada; aprovação/rejeição não foi demonstrada. |

## Tarefas do Estudante 3

1. Implementar RF16 em defesa em profundidade: validar tipo, tamanho e escopo; moderação ou alternativa documentada; ataques diretos e indiretos; conteúdo recuperado sempre como dado não confiável; validação de saída/citações; filtro de dados indevidos; timeouts, limite de tokens/chamadas e no máximo uma repetição transitória. Registrar motivo sem reproduzir segredo. Moderação não substitui detector de injeção/escopo; não usar apenas palavras-chave ou instruções no prompt.
2. Implementar RF20 em Streamlit. Usar serviços existentes para listar/indexar, compreender solicitação, consultar RAG, mostrar ficha/resumo/categoria/entidades, status e fontes. `st.file_uploader` inicia em memória; criar arquivo temporário somente para PyMuPDF e removê-lo em `finally`. Interface não deve refazer chunking ou recuperação.
3. Implementar RF22 com Pydantic/Literal por avaliação individual, saída positiva/negativa/neutra/indeterminada, justificativa curta, proveniência e revisão. Mensagem mista, ironia e contexto ausente não devem ser forçados a polaridade. Não inferir personalidade, diagnóstico ou perfil sensível.
4. Calcular agregações em Python (pandas só se útil/necessário), mostrar numerador/denominador e tratar coleção vazia sem divisão por zero. Não solicitar ao LLM contagens ou percentuais; confiança é estimativa não calibrada, não probabilidade/população.
5. Usar `dados/originais/avaliacoes/avaliacoes_ficticias.json` e seu gabarito; nenhum rótulo de modelo ou métrica de sentimento existe ainda.

## Integração posterior — RF23/RF24

- Ligar `processar_arquivo_solicitacao()` ao texto digitado e aos TXT revisados/corrigidos de áudio/OCR. Os JSON legados `entrada_audio_transcricao.json` e `entrada_pdf_ocr.json` contêm campos/metadados, não texto integral; use `entrada_audio_transcricao_revisada.txt` e `entrada_pdf_ocr_corrigido.txt`, mantendo a incerteza OCR visível.
- Validar no fluxo os estados `pendente`, `aprovada`, `rejeitada` e `revisar`, com justificativa e identidade do operador. O serviço RAG persiste `aprovada`/`rejeitada`/`revisar`; integrar com `src/review.py` quando a ficha/minuta do novo fluxo for consolidada.
- Não enviar respostas automaticamente. Exigir aprovação humana antes de encaminhamento institucional.
- Definir retenção e remoção. Exclusão deve remover o documento, chunks de todas as estratégias/coleções e resultados derivados associados, deixando trilha de exclusão. Demonstrar que os chunks deixam de aparecer em novas consultas. Esta operação ainda não existe.
- A su?te inclui 157 testes, entre eles 11 testes direcionados com mocks para schema/neg?cio, entidades, absten??o, conflito, cita??es e auditoria. Permanecem demonstra??es manuais de PDF sem camada textual, persist?ncia, bloqueio de caminhos, remo??o e matriz integrada RF23/RF24.
- Reexecutar um caso textual e um caso de áudio ou OCR do Desafio 1 e preencher a matriz RF23 com entrada, esperado, obtido, situação, numerador/denominador e artefato real.

## Contratos para a interface

1. `processar_arquivo_solicitacao(path, solicitacao_id=..., config=...)` devolve dicionário com `ficha`, `alertas_negocio`, `status`, `minuta` (ou null), `metadata`, `schema_version`, `prompt_version` e decisão `pendente`. Campo anulável ausente deve ser apresentado como “não localizado”.
2. `indexar_acervo(strategy=..., config=...)` retorna coleção, estratégia, documentos, hashes, chunks e configuração de embedding. `listar_documentos_indexados()` mostra documentos persistidos.
3. `consultar_rag(pergunta, ficha_solicitacao=..., config=..., top_k=...)` devolve estado, resposta/minuta ou abstenção, fontes, excertos, distância/similaridade, modelo, duração e decisão pendente. A interface mostra documento, versão, chunk ID, página/seção e texto literal vindos dos metadados, sem confiar em página escrita pelo modelo.
4. `registrar_revisao_rag(execution_id, decision, justification, config=...)` persiste `aprovada`, `rejeitada` ou `revisar`; só permite aprovação de resposta `fundamentada`. Não acoplar serviço à sessão Streamlit.
5. `avaliar_chunking()` executa a comparação das estratégias quando o usuário solicitar e grava só então `resultados/avaliacoes_recuperacao.json`; antes disso, nenhuma taxa/estratégia vencedora existe.

## Orientação técnica e segurança

- Dependências diretas adicionadas ao projeto: `pydantic`, `chromadb` e `PyMuPDF`; `openai` e `python-dotenv` já existiam. Streamlit não foi instalado. Pandas fica para a agregação do Estudante 3, se necessário.
- `OPENAI_API_KEY` deve ser configurada manualmente pelo usuário em `.env` local ou ambiente. Não ler, imprimir, versionar ou colocar seu valor em configuração, dados, prompt, log ou documentação. `.gitignore` mantém `.env` excluído.
- Somente material fictício do manifesto pode ser indexado. Os demais PDFs em `arquivos/` são materiais de desafio/editais, não corpus institucional.
- O limiar `0.40` separou os oito cenários fictícios observados: as perguntas respondíveis tiveram similaridade máxima >=0.444 e as sem resposta <=0.334. É uma calibração pequena e específica, não uma garantia geral; distância cosine não é probabilidade de correção. Mudança de geração não invalida embeddings; mudança do embedding ou chunking exige coleção compatível/reindexação.
- Modelo/endpoint e permissões usados nessa configuração responderam às execuções registradas. O custo monetário não foi calculado. O provedor `simulated` é dry-run, não responde e não é evidência de qualidade.

## Próxima sequência sugerida

1. Estudante 3 implementa guardrails e Streamlit usando os contratos acima.
2. Estudante 3 implementa RF16, RF20/Streamlit e RF22 usando os serviços e contratos existentes.
3. Revisar manualmente as seis fichas e cinco respostas fundamentadas; resolver campos/resumos divergentes antes de aprovar qualquer resultado.
4. Escolher chunking somente após comparar contexto recuperado; a métrica atual de 5/5 é apenas hit@3 neste pequeno gabarito.
5. Concluir remoção/retensão, decisões humanas com operador identificado e matriz RF23/RF24; reexecutar regressão textual e áudio/OCR do Desafio 1.

## Adendo de correções — 30/10/2026

O documento acima registra o estado anterior em v1. O contrato vigente passou a `solicitacao.v2` com prompt `compreensao_solicitacao.v3`; o gabarito de solicitações foi revisto. Relatórios e fichas preexistentes continuam históricos e não foram sobrescritos nem reavaliados contra o novo gabarito. As alterações recentes acrescentam sanitização central de logs, limite de chamadas por execução, exclusão do texto original nos novos artefatos NLP, verificação local de conflitos e encaminhamento a revisão humana para abstenção com evidência disponível. RF18 segue empatado em hits@3; consulte `analise_rf18_relevancia.md`. A suíte local tem 157 testes, dos quais 11 são direcionados às correções e usam mocks. Nenhuma chamada paga foi feita nesta etapa. RF16, RF20 e RF22 continuam pendentes para Estudante 3; revisão semântica humana e testes adicionais de RF17/RF18/RF21 permanecem abertos.

## Handoff verificado após reexecução — 30/10/2026

A última execução pós-limpeza foi validada em `documentacao/relatorio_reexecucao_desafio2_2026-10-30.md`. Há seis fichas atuais, Chroma persistente com os seis documentos e oito execuções RAG individuais com logs válidos. RF17/RF18 podem ser consumidos pela interface do Estudante 3. Permanecem tarefas próprias de RF16, RF20 e RF22, e as pendências semânticas RF14/RF15/RF19 descritas no relatório devem continuar visíveis; destaque especial para SOL-001 e RAG-05. A suíte passou com 157 testes. Nenhuma chamada OpenAI ocorreu durante a validação local e o pós-processamento.
