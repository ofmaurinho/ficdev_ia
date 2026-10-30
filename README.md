# Central Inteligente de Atendimento e Comunicação Institucional

## Objetivo

Este projeto implementa um protótipo multimodal para o desafio prático de inteligência artificial generativa, com foco em:

- processamento textual, transcrição de áudio e OCR/visão de solicitações institucionais;
- classificação, registro e validação local;
- preparação de minutas institucionais sem automatizar envio real;
- síntese de voz de minutas aprovadas e geração de peças visuais identificadas como sintéticas;
- auditoria e rastreabilidade das execuções;
- comparativo de prompts A, B e C documentado para uso acadêmico.

## Escopo e status

O projeto implementa os fluxos de texto, STT, OCR local com fallback Vision, TTS sujeito a aprovação humana, geração de imagem com composição local, revisão e auditoria. O comando `processar-texto` não chama a API; os demais fluxos podem enviar conteúdo fictício ao provedor e gerar custos. A geração de nova versão continua sendo iniciada conscientemente pelo operador.

### Cobertura dos requisitos do desafio

| Requisito | Implementação e resultado da última execução limpa |
|---|---|
| RF01 | CLI, `config.json`, `.env.example` e segredos em ambiente implementados; execução limpa em Python 3.14.7. |
| RF02 | A/B/C e metaprompt C executados no texto normal; os três passaram no esquema nessa execução. Experimento de injeção executado, mas as saídas falharam na validação do gabarito. A seleção humana permanece pendente. |
| RF03 | Separação system/user, delimitação de conteúdo não confiável e regra de lacunas implementadas. A injeção não foi obedecida, porém a extração falhou em campos críticos. |
| RF04 | Chamadas reais, timeout, erros mapeados, duração e tokens auditados. Custo monetário não calculado. |
| RF05 | Extração local e minuta executadas; JSON, campos ausentes, texto original e fontes registrados. |
| RF06 | STT real executado; WER 0,0154 e 2/3 campos críticos corretos (90/100). A data divergiu do gabarito; requer correção e conferência humana. |
| RF07 | Nesta execução limpa, a síntese foi bloqueada corretamente por falta de aprovação humana válida da minuta e do roteiro. Uma execução anterior gerou áudio (WER de retorno 0,0337); a escuta humana segue pendente. |
| RF08 | OCR Tesseract e Vision executados; avaliação 70/100, com divergência nos 3 campos críticos. A confirmação humana é necessária antes de usar os dados. |
| RF09 | Minuta e roteiro gerados com fonte e revisão obrigatória; sem envio automático. Defeito de registro do PDF no fluxo integrado corrigido e coberto por teste. |
| RF10 | Modelo atualizado para `gpt-image-2.5-flare` após identificar que `gpt-image-1` foi retirado da API. Geração e proveniência executaram; a composição local foi corrigida para renderizar acentos no Windows. A aprovação visual por operador segue pendente. |
| RF11 | Logs JSONL registram execução, provedor, modelo, parâmetros, duração, uso, erros e decisões sem armazenar chave. |
| RF12 | Entradas fictícias, análise de privacidade e minimização implementadas; o uso de Vision envia a página ao provedor externo. |
| RF13 | Avaliações contra gabarito, severidade e taxa de aprovação implementadas. A rodada encontrou erros de extração; revisão do áudio, peça visual e experimento continuam necessárias. Há casos históricos aprovados/rejeitados em `resultados/revisoes/`. |

O resultado da rodada representa uma amostra por modalidade. “Executado” não significa “aprovado”: campos críticos divergentes e saídas que falham no gabarito precisam de correção humana antes de uso.

## Responsabilidades dos estudantes

- Estudante 1: prompts, avaliação e documentação.
- Estudante 2: integração, segurança, texto, classificação e auditoria.
- Estudante 3: áudio, OCR/visão, geração de imagem, acessibilidade e avaliação multimodal.

## Estrutura do projeto

- `arquivos/`: materiais originais de entrada preservados.
- `dados/originais/`: cópias de materiais quando necessário.
- `dados/gabaritos/`: resultados esperados definidos antes da execução.
- `dados/processados/`: dados extraídos estruturados.
- `resultados/minutas/`: minutas em rascunho.
- `resultados/logs/`: logs JSON Lines.
- `src/`: módulo principal.
- `prompts/`: textos canônicos do sistema, tarefa comum e prompts A/B/C, carregados por `src/prompts.py`.
- `documentacao/`: documentos de decisão e minimização de dados.
- `documentacao/registro_uso_ia.md`: registro de uso de assistente no desenvolvimento.
- `testes/`: testes automatizados.

## Pré-requisitos

- Python 3.10 ou superior. Validado neste projeto com Python 3.14.7.
- `pip` atualizado.
- Internet e uma chave válida da OpenAI para prompts, STT, Vision, TTS e geração de imagem.
- Tesseract OCR com dados de idioma português para a rota local de OCR.
- `requirements.txt` declara faixas de versões; use `requirements.lock` para recriar o ambiente exato validado nesta máquina.

O Tesseract deve estar no `PATH` e ter o idioma `por` instalado. Confirme com `tesseract --list-langs` antes de executar OCR.

## Instalação

PowerShell (Windows):

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
# Mantém acentos e símbolos legíveis nos comandos Python no Windows.
$env:PYTHONUTF8 = "1"
```

Se a política de execução do PowerShell bloquear a ativação, use o Prompt de Comando:

```bat
py -3 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
set PYTHONUTF8=1
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
```

## Configuração

Para executar o fluxo local, não é necessário configurar uma chave. Para chamadas reais, copie `.env.example` para `.env` e edite o arquivo localmente, sem incluir a chave no repositório:

```powershell
Copy-Item .env.example .env
```

Configure `OPENAI_API_KEY` e, opcionalmente, `OPENAI_MODEL`. A variável `OPENAI_MODEL` tem precedência; sem ela, o modelo vem de `config.json`. Modelo, temperatura, limite de saída, timeout e caminhos de entrada/saída/gabarito são parâmetros não secretos definidos em `config.json`. Caminhos relativos são resolvidos a partir da raiz do projeto. Nunca compartilhe nem versione `.env`.

## Execução

```bash
python -m src.main --help
python -m src.main
python -m src.main processar-texto
python -m src.main logs
```

Com chave configurada, execute a comparação real (quatro chamadas: A, B, metaprompt C e tarefa C):

```bash
python -m src.main prompts
```

Para executar as modalidades do desafio com os arquivos fictícios incluídos:

```powershell
python -m src.main fluxo --arquivo arquivos/entrada_texto.txt --caso caso_marcos
python -m src.main audio --arquivo arquivos/entrada_audio.mp3 --caso entrada_audio
python -m src.main ocr --arquivo arquivos/entrada_pdf-imagem.pdf --caso entrada_pdf
python -m src.main imagem --caso caso_marcos
python -m src.main aprovar-minuta --caso caso_marcos --versao 1 --operador "operador" --decisao aprovar --justificativa "Dados conferidos com a fonte"
python -m src.main voz --caso caso_marcos --versao 1 --confirmar
```

Use `--forcar-vision` para exercitar a rota externa de visão mesmo sem gatilhos locais. O TTS exige aprovação válida da minuta e do roteiro. Registre aprovação de minuta ou revisão visual somente depois de uma pessoa inspecionar o artefato.

Para selecionar outra entrada textual, use `python -m src.main prompts --arquivo caminho/para/entrada.txt`. Sem chave, o comando identifica a execução como pendente e não simula sucesso. A chamada à API pode gerar custos.

Depois de inspecionar `resultados/avaliacao_prompts.json`, registre uma decisão humana e sua justificativa:

```powershell
python -m src.main revisar --prompt B --decisao aprovar --justificativa "Atende ao gabarito; revisão final concluída."
```

`--decisao` aceita `aprovar`, `rejeitar` ou `gerar_novamente`. A decisão fica no JSON de avaliação e no log com o mesmo ID da execução. `gerar_novamente` registra a solicitação; o operador deve revisar a causa e iniciar outra execução de `prompts` conscientemente.

## Testes

```bash
python -m unittest discover -s testes -v
```

## Reproduzibilidade

Para uma verificação limpa, crie um ambiente virtual, instale `requirements.lock`, execute `python -m unittest discover -s testes -v` e depois `python -m src.main processar-texto`. Para testar as rotas multimodais, execute os comandos acima com os arquivos fictícios, compare STT/OCR/extração com os gabaritos usando `python -m src.main avaliar --tipo ... --gabarito ... --arquivo ...` e inspecione os resultados. As chamadas à API dependem de rede e podem gerar cobrança. Em 29/10/2026, a suíte passou com 146 testes após as correções do registro de PDF, modelo de imagem e diagnóstico de modelo inválido. Na reexecução limpa integral de 29/10/2026, `pip check` e o verificador de entrega passaram; prompts A/B/C, fluxo textual, STT, OCR com Tesseract/Vision e geração de imagem foram executados em uma pasta temporária nova. Os três prompts passaram no esquema. A avaliação STT obteve WER 0,0154 e 2/3 campos críticos (90/100); OCR obteve 70/100 e divergências nos 3 campos críticos, portanto nenhum deles foi aprovado. O comando TTS respeitou o bloqueio por falta de aprovação humana válida; não houve nova síntese nesta rodada. A imagem foi gerada com `gpt-image-2.5-flare`, o hash de proveniência confere e a inspeção visual continua pendente. O verificador terminou com 9 avisos de revisão/aprovação pendentes. Os artefatos dessa execução ficaram isolados em uma pasta temporária; a reprodução grava em `dados/processados/` e `resultados/`.

## Continuidade — Desafio Prático 2

Esta evolução cobre o recorte dos Estudantes 1 e 2: RF14/15 (ficha Pydantic, validação de negócio, NLP e comparação com gabarito) e RF17/18/19/21 (extração, chunking, Chroma persistente, avaliação de recuperação, RAG, provedor e auditoria). Os módulos de texto, áudio e OCR do Desafio 1 permanecem; `src.nlp.processar_arquivo_solicitacao()` aceita TXT e JSON que contenha texto. Para os resultados atuais de STT/OCR, use os TXT revisados/corrigidos em `dados/processados/`, pois os JSON legados guardam campos/metadados, não o texto integral.

O acervo fictício explícito está em `dados/originais/acervo/manifest.json`: seis documentos, três TXT e três PDFs textuais. A ingestão lê somente os caminhos do manifesto e rejeita caminhos fora do diretório do acervo. PDFs de desafio, aulas e editais em `arquivos/` não são indexados. Solicitações e gabaritos ficam em `dados/originais/solicitacoes/` e `dados/gabaritos/desafio2_solicitacoes.json`; oito perguntas RAG e IDs determinísticos dos chunks esperados estão em `dados/gabaritos/desafio2_rag.json`. As doze avaliações e três referências adversariais estão separadas em `dados/originais/avaliacoes/`; classificação de sentimentos e guardrails completos não foram implementados nesta etapa.

Os comandos de serviço são independentes do CLI do Desafio 1 e foram confirmados em `src/desafio2_cli.py`:

```powershell
python -m src.desafio2_cli demonstrar-schema
python -m src.desafio2_cli indexar
python -m src.desafio2_cli listar
python -m src.desafio2_cli avaliar-recuperacao
python -m src.desafio2_cli compreender --arquivo dados/originais/solicitacoes/SOL-001_audio_desafio1.txt
python -m src.desafio2_cli avaliar-solicitacoes
python -m src.desafio2_cli consultar --pergunta "Em quais dias e horários funciona o Núcleo Fictício de Atendimento?"
python -m src.desafio2_cli revisar --execution-id ID_DA_EXECUCAO --decisao revisar --justificativa "Conferir a fonte com a unidade."
```

`demonstrar-schema` é local e não chama API. `indexar`, `compreender`, `avaliar-solicitacoes`, `avaliar-recuperacao` e `consultar` usam embeddings ou geração OpenAI conforme a operação e podem gerar custos; exigem chave válida no `.env` ou no ambiente. Em 30/10/2026, a configuração OpenAI foi exercitada com respostas estruturadas e embeddings; tokens e duração são registrados quando fornecidos pelo SDK, mas o custo monetário não é calculado.

`config.json` contém configuração não secreta sob `desafio2`: geração OpenAI (`gpt-4o-mini`), embeddings `text-embedding-3-small` com dimensão 1536 e Chroma persistente em `dados/indice/chroma`. A recuperação usa top-k=3 e limiar 0,40, calibrado apenas para separar os oito cenários fictícios atuais (as cinco consultas respondíveis tiveram similaridade máxima >=0,444; as duas sem resposta ficaram <=0,334). Esse ajuste não generaliza automaticamente. O adaptador passa vetores explicitamente ao Chroma; o banco retorna distância cosine e o código expõe similaridade como `1 - distância`. Trocar modelo de geração mantém o índice; mudar embedding/dimensão ou chunking abre uma coleção incompatível e requer reindexação.

A comparação RF18 usa `structural` (seção/parágrafo, sem sobreposição) e `fixed_400_overlap_80` (caracteres, sobreposição de 80), nas mesmas cinco perguntas respondíveis, embedding e top-k. A execução de 30/10/2026 obteve 5/5 hits em ambas as estratégias em `resultados/avaliacoes_recuperacao.json`; empate de hits não escolhe uma estratégia sem revisão de contexto.

RF19 pode retornar `fundamentada`, `sem_evidencia`, `conflito_de_fontes` ou `revisao_humana`. A execução dos oito cenários está em `resultados/avaliacao_cenarios_rag.json`: 8/8 estados corresponderam ao gabarito; as cinco respostas fundamentadas citaram chunks recuperados e não tiveram IDs de citação inválidos. As duas ausências foram bloqueadas antes da geração e o conflito de matrícula foi encaminhado sem escolher uma regra. Cada fonte contém documento, versão, ID estável do chunk, página/seção, excerto literal, distância e similaridade. A consulta é salva em `resultados/rag/<execution_id>.json` e `resultados/logs/consultas.jsonl`, com pergunta minimizada/mascarada, hash, fontes, status e decisão pendente. A geração fundamentada continua sujeita a revisão humana. O provedor alternativo `simulated` foi exercitado como dry-run identificado: não gera resposta e não equivale ao modelo real; a recuperação ainda exige embeddings.

RF14/RF15 foram executados nos seis casos fictícios com `compreensao_solicitacao.v2`. O relatório atual `resultados/avaliacao_nlp_desafio2.json` registra 4/6 categorias, 19/24 campos literais, 6/20 correspondências lexicais de fatos do resumo e revocação literal de entidades 10/25; a correspondência lexical não substitui revisão semântica. As duas rodadas anteriores estão preservadas em `resultados/avaliacao_nlp_desafio2_rodada_1.json` e `_rodada_2.json`. O sistema mantém as seis fichas em revisão humana; nenhuma delas foi aprovada automaticamente.

Estudante 3: RF16 completo, RF20/Streamlit e RF22/painel não foram implementados. RF23/RF24, remoção de documento com derivados e demonstração de decisões humanas são pendências compartilhadas. O estado real, contratos de serviço e sequência de continuação estão em [CONTINUIDADE_ESTUDANTE_3.md](documentacao/CONTINUIDADE_ESTUDANTE_3.md). O roteiro com os artefatos e comparações para aprovação manual de RF14/RF15/RF17/RF18/RF19/RF21 está em [revisao_manual_desafio2_estudantes_1_2.md](documentacao/revisao_manual_desafio2_estudantes_1_2.md). Detalhes do schema e da demonstração JSON/schema estão em [desafio2_rf14_rf15.md](documentacao/desafio2_rf14_rf15.md).

## Modelos e parâmetros

- Provedor: OpenAI Responses API.
- Modelo: `OPENAI_MODEL`, com fallback para `config.json` (`gpt-4o-mini` no exemplo).
- Temperatura, `max_output_tokens` e timeout vêm de `config.json`.
- Versões da última execução limpa: Python 3.14.7, OpenAI SDK 3.41.0, python-dotenv 1.2.4, Pillow 13.0.0, pytesseract 0.3.13, pypdfium2 5.14.0 e mutagen 1.48.1. `requirements.lock` registra as dependências exatas dessa execução; `requirements.txt` mantém faixas para instalação flexível.
- O uso de tokens é registrado quando fornecido pelo provedor. O custo não é calculado porque não há tabela de preços versionada; o registro declara essa limitação.

## Logs e rastreabilidade

- Pasta de logs: `resultados/logs/`.
- Formato: JSON Lines (`.jsonl`).
- Nunca são registrados segredos, chaves ou tokens.

## Metodologia de prompts

Os textos canônicos ficam em `prompts/system.txt`, `prompts/task_spec.txt`, `prompts/prompt_a.txt`, `prompts/prompt_b.txt` e `prompts/prompt_c.txt`; `src/prompts.py` os carrega e associa versões e esquema JSON. Eles seguem a estrutura:

- Prompt A: zero-shot curto.
- Prompt B: estruturado em persona, contexto, tarefa, formato e critérios de sucesso.
- Prompt C: metaprompt executado para gerar um prompt aprimorado; o prompt gerado é então aplicado à mesma tarefa e entrada de A e B.

As chamadas usam a mesma configuração e o mesmo texto minimizado. Saídas, prompts aplicados, metadados de resposta e identificador da auditoria são salvos em `resultados/avaliacao_prompts.json`. A revisão humana permanece pendente até que a equipe registre sua decisão com o comando `revisar`; a matriz comparativa está em `documentacao/matriz_avaliacao_prompts.md`.

## Critérios de avaliação

- fidelidade ao contexto;
- ausência de dados inventados;
- completude;
- formato;
- tom institucional;
- identificação de campos ausentes;
- segurança;
- duração;
- utilidade.

Escala sugerida: 1 a 5, com justificativa por critério.

## Limitações conhecidas

- A integração real com a OpenAI exige chave válida e configuração do ambiente.
- O experimento controla a variável modelo usando `gpt-4o-mini`; não há benchmark empírico entre provedores/modelos nem cálculo de preço vigente.
- A imagem precisa de inspeção visual humana antes de ser marcada como utilizável.
- STT e OCR podem retornar campos críticos ausentes ou divergentes e exigem confirmação humana antes da minuta.
- O projeto é acadêmico e não substitui revisão humana nem conformidade jurídica completa.

## Segurança e privacidade

- O conteúdo recebido é tratado como não confiável.
- Chaves e segredos não são registrados nos logs.
- Os dados no repositório são fictícios, conforme o desafio.
- O protótipo não deve ser usado para ações institucionais reais.

## Privacidade e limites

Use somente dados fictícios. O processamento local preserva o texto de entrada no JSON estruturado; antes das chamadas à API, o projeto remove data/local de nascimento e campos adicionais com CPF, RG, nome da mãe e e-mail. Nome do solicitante, protocolo e data do atendimento permanecem porque são necessários ao cenário e devem ser fictícios. Logs não armazenam texto bruto nem chave.

O sistema não envia respostas automaticamente. As saídas são rascunhos e precisam de conferência humana. A revisão só muda de pendente quando um operador registra explicitamente a decisão. A solução não substitui avaliação de segurança, jurídica ou de conformidade LGPD.

## Atualização de correções do Desafio 2 (30/10/2026)

O estado vigente de RF14/RF15 está configurado em `config.json`: prompt `compreensao_solicitacao.v3` e schema `solicitacao.v2`. O gabarito `dados/gabaritos/desafio2_solicitacoes.json` também foi revisado para v2. Os relatórios e fichas gerados antes dessa alteração continuam preservados como histórico: suas métricas se referem ao gabarito/prompt anteriores e não validam a versão atual. Nenhuma nova geração paga foi feita durante essa correção.

Para RF18, a análise dos resultados existentes está em [analise_rf18_relevancia.md](documentacao/analise_rf18_relevancia.md). As duas estratégias mantêm 5/5 hits@3; há resultados não responsivos entre os primeiros colocados e o chunk de canais de RAG-05 aparece em terceiro. A análise não escolhe vencedor nem altera o benchmark ou índice histórico.

As correções acrescentam limite configurável de chamadas OpenAI por execução, sanitização central de auditoria, remoção do texto original dos novos artefatos NLP, revisão humana para abstenções/conflitos não verificados e metadados de decisão em falhas RAG. Durante esta etapa, a suíte local passou com **157 testes**, incluindo 11 novos testes direcionados com provedores simulados. Os testes não chamam a API. O índice Chroma, as entradas originais e os resultados históricos não foram regravados.

## Validação da reexecução — 30/10/2026

O relatório detalhado da rodada após a limpeza está em [relatorio_reexecucao_desafio2_2026-10-30.md](documentacao/relatorio_reexecucao_desafio2_2026-10-30.md). A revisão encontrou e corrigiu caracteres de acentuação no gabarito v2 e duas regras de normalização local de entidades; as fichas da rodada foram reavaliadas sem novas chamadas OpenAI. Métricas atualizadas: categorias 6/6, campos literais 19/25, correspondência lexical de fatos 6/20 e entidades 25/25 após a normalização determinística. Fidelidade semântica continua pendente.

RF17 foi confirmado com seis documentos e 17 chunks estruturais; RF18 empatou em 5/5 nas duas estratégias. RF19 teve 8/8 estados corretos e citações válidas entre as cinco respostas fundamentadas, mas RAG-05 ainda omite o encaminhamento à coordenação e RAG-01 tem uma citação extra que precisa de revisão. As aprovações humanas seguem pendentes. O Estudante 3 pode iniciar RF16/RF20/RF22 em paralelo; não marcar RF14/RF15/RF19 como aprovação humana final.
