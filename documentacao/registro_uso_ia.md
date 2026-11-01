# Registro de uso de IA no desenvolvimento

## Ferramenta e ambiente

- Assistente: GitHub Copilot no Visual Studio Code.
- Modelo e versão do assistente: Codex baseado em GPT-6 Luna.
- Ambiente da validação mais recente: Python 3.14.7, OpenAI SDK 3.41.0, python-dotenv 1.2.4 e dependências de `requirements.lock`.
- Uso: planejamento, implementação, revisão do enunciado e documentação. Chamadas de geração A/B/C foram feitas ao modelo OpenAI indicado no artefato de avaliação, não ao assistente de codificação.

## Solicitações relevantes

As solicitações abaixo são sínteses fiéis do trabalho solicitado, não transcrições literais:

1. Inspecionar o repositório e implementar os requisitos dos Estudantes 1 e 2 do desafio prático.
2. Configurar e validar a chamada real à OpenAI após a configuração do `.env`.
3. Executar o projeto e verificar os testes e a integração real.
4. Reabrir o PDF, comparar os requisitos com código e documentação, revisar `requirements.txt` e tornar a execução reproduzível pelo README.
5. Reexecutar em cópia limpa todas as modalidades do desafio, corrigir documentação desatualizada e testar os defeitos encontrados.
6. Evoluir incrementalmente o mesmo projeto para os requisitos dos Estudantes 1 e 2 do Desafio Prático 2, sem chamadas pagas nem novos testes automatizados.
7. Comparar os requisitos do PDF do Desafio 2, criar dados/gabaritos fictícios e preparar contratos reais de handoff para o Estudante 3.
8. Corrigir documentação e dependências sem indexar indiscriminadamente PDFs de editais/aulas presentes em `arquivos/`.

## Sugestões e decisões

- Aceitas: separação em módulos para prompts, cliente OpenAI, processamento textual e auditoria; chave carregada pelo ambiente; testes locais sem depender de chamadas remotas.
- Modificadas após validação: Prompt C passou a ser realmente gerado por metaprompt e aplicado à mesma tarefa; A/B/C passaram a usar esquema estruturado comum, gabarito prévio e verificação automática. Os campos pessoais desnecessários foram removidos antes do envio à API.
- Rejeitadas: tratar uma resposta executada como automaticamente aprovada; declarar cálculo de custo sem preço configurado; marcar artefato como aprovado sem revisão humana; manter textos que diziam que nenhuma chamada real ocorreu após a chamada ter sido validada.
- Aceitas nesta revisão: atualizar o README e a matriz para distinguir execução de aprovação; atualizar o lockfile ao conjunto de versões instalado; registrar PDFs de minuta no inventário de artefatos.
- Aceitas no Desafio 2: Pydantic estrito e regras de negócio pós-schema; Chroma persistente com embeddings explícitos; PyMuPDF por página; dois chunkers comparáveis; RAG com fontes, abstenção e log.
- Modificadas: a configuração de geração mantém `gpt-4o-mini` do Desafio 1; gabarito OCR não trata campos incertos como fatos; os IDs de referência são derivados de documento/hash/localização/conteúdo, sem inventar taxas.
- Rejeitadas: chamar OpenAI para gerar respostas/embeddings nesta etapa, classificar sentimentos/painel do Estudante 3, importar os editais como corpus, medir ou afirmar vencedor de chunking sem executar a avaliação.

## Validação feita

- Testes automatizados: 146 testes passaram com `requirements.lock` em ambiente virtual temporário.
- Fluxos reais em cópia limpa: texto, A/B/C, prompt injection, STT, OCR/Vision, TTS e relatório. A/B/C normal passou na validação automática (3/3); avaliação da injeção marcou 60/100 e segurança 100/100; STT 90/100 e OCR 70/100, reprovados por campos críticos. Extração local marcou 100/100.
- TTS produziu áudio para roteiro já aprovado por operador; WER de retorno 0,0337.
- A primeira tentativa de imagem falhou porque `gpt-image-1` havia sido retirado do serviço. Configuração atualizada para `gpt-image-2.5-flare`; a geração real e a nota de proveniência passaram. A inspeção visual encontrou caracteres acentuados quebrados na composição Windows; a fonte foi corrigida e a imagem recomposta localmente com o mesmo fundo, sem segunda chamada à API.
- Corrigido `minuta_pdf` no inventário de artefatos após o fluxo integrado detectar tipo desconhecido; um teste de regressão foi incluído e o fluxo voltou a gerar e registrar o PDF.
- Revisão dos prompts, áudio e imagem continua pendente para um operador humano. A rodada limpa foi isolada em pasta temporária para preservar resultados já existentes.
- Desafio 2 (29/10/2026): dependências `chromadb` e `PyMuPDF` instaladas no `.venv`; `Responses.parse` existe no SDK local; demonstração local distinguiu JSON sintático de schema (chave extra, tipo incorreto e campo obrigatório ausente). Ingestão local leu 6 documentos e produziu 17 chunks estruturais e 11 fixos; são contagens de chunking, não métricas de recuperação.
- Revisão final da implementação do Desafio 2: `pip check` sem dependências quebradas; `compileall` e CLI concluídos; manifesto e gabaritos JSON lidos localmente; conferidos 6 documentos (3 TXT/3 PDF), 6 solicitações, 8 perguntas RAG (5 respondíveis/2 sem resposta/1 conflito), 12 rótulos de sentimento (3 por classe) e 3 referências adversariais. Não foram executadas chamadas OpenAI, indexação vetorial ou avaliações de qualidade.
- Execução final do Desafio 2 (30/10/2026): chamadas reais de geração e embeddings foram realizadas com a configuração OpenAI do projeto. RF14/RF15 processaram seis solicitações com o prompt v2; a rodada final teve 4/6 categorias, 19/24 campos literais, 6/20 correspondências lexicais de fatos resumidos e 10/25 entidades esperadas recuperadas. As duas rodadas anteriores estão preservadas; fidelidade semântica não foi aprovada automaticamente.
- RF17/RF18: 6 documentos fictícios indexados em Chroma, 17 chunks estruturais; reindexação substituiu os chunks anteriores sem duplicá-los. As duas estratégias obtiveram 5/5 hit@3 nas perguntas respondíveis.
- RF19: oito consultas reais com `rag_institucional.v2` produziram os oito status esperados e nenhuma citação fora dos chunks recuperados; duas ausências foram abstidas antes de geração e o conflito de matrícula foi encaminhado. A configuração de similaridade 0,40 foi ajustada somente para esse conjunto fictício e requer reavaliação com outros dados.
- RF21: Responses API e embeddings funcionaram; o adaptador `simulated` e a falha de índice vazio também foram exercitados. Uso/token pode estar nos logs do SDK; custo monetário não foi calculado. A chave não foi impressa nem alterada. Não foram criados novos arquivos de teste.

## Responsabilidade

A IA auxiliou o desenvolvimento, mas não substitui a compreensão, a revisão e a responsabilidade da equipe. **Declaração da equipe a confirmar antes da entrega:** os integrantes revisaram o código, os resultados, as limitações e as decisões registradas e assumem responsabilidade pelo material final.

### Correções posteriores (30/10/2026)

O assistente revisou RF14/RF15/RF17/RF18/RF19/RF21 e implementou ajustes locais: schema/gabarito v2 e prompt v3 para NLP, enriquecimento local de entidades literais, limites de chamadas, sanitização de auditoria, proteção das decisões RAG contra abstenção/conflito não verificados e testes unitários simulados. Foi criada análise offline da relevância RF18. Foram executados 157 testes locais (11 direcionados); não houve chamadas à OpenAI durante esta etapa. O índice Chroma, arquivos originais, fichas e relatórios históricos não foram regravados. As métricas históricas não validam o gabarito v2; a revisão semântica humana segue necessária.

### Reexecução e validações locais (30/10/2026)

Na validação posterior à limpeza, foram encontradas substituições de acentos por `?` em chaves/valores do gabarito NLP v2. O gabarito foi reparado com base nos TXT fictícios. Também foram corrigidas as regras determinísticas de normalização de entidades para não classificar parte do nome de um curso como local, completar o eixo tecnológico e manter a forma literal do turno. As fichas atuais foram revalidadas e as métricas recalculadas offline; não houve chamada OpenAI nesta etapa. A suíte passou com 157 testes. O relatório descreve lacunas semânticas remanescentes que exigem revisão da equipe.

### Conclusão das entregas do Estudante 3 e integração RF23/RF24 (01/11/2026)

Foram implementados os módulos `src/guardrails.py` (RF16), `src/sentiment.py` (RF22), `src/metrics.py` (RF23), `src/app.py` (RF20) e a exclusão de documentos e derivados em `src/vector_store.py` (RF24), além de `testes/test_estudante3_desafio2.py`. Com a chave configurada em `.env`, foram executados o índice persistente, a classificação das 12 avaliações fictícias (12/12 acertos no gabarito), a demonstração de exclusão de `ACV-ATEND-005` (2 chunks antes, 0 após exclusão), a regressão dos 3 casos do Desafio 1 (3/3 concluídos) e a consolidação da matriz T01–T15 (15/15 aprovados). A suíte automatizada passou com 169 testes sem expor credenciais.

