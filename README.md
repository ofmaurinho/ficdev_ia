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

A evolução do protótipo cobre os requisitos RF14 a RF24 (Estudantes 1, 2 e 3):

- **RF14 e RF15 (`src/schemas.py`, `src/nlp.py`):** extração estruturada com Pydantic estrito (`solicitacao.v2`), validação de regras de negócio pós-schema, classificação em conjunto fechado, resumo de até 100 palavras e extração de entidades literais.
- **RF16 (`src/guardrails.py`):** guardrails em três camadas (entrada, recuperação e saída), validação de extensão/tamanho de arquivo, filtro de escopo, contenção de injeção direta e indireta, bloqueio de exfiltração de segredos e limite de chamadas por execução (`max_calls_per_run`).
- **RF17 e RF18 (`src/ingestion.py`, `src/vector_store.py`, `src/rag_evaluation.py`):** ingestão restrita aos seis documentos do manifesto (`dados/originais/acervo/manifest.json`), índice persistente em ChromaDB (`dados/indice/chroma`) com embeddings `text-embedding-3-small` (1536 dimensões) e seleção da estratégia `structural` (17 chunks, 5/5 no top-3) por preservar seções normativas completas sem truncamento.
- **RF19 e RF21 (`src/rag.py`, `src/providers.py`):** RAG fundamentado com citações verificadas nos chunks recuperados, abstenção antes da geração quando a similaridade máxima fica abaixo de 0,40, detecção explícita de conflito entre fontes vigentes e troca de provedor de geração (`openai` ou `simulated`) sem reindexar o acervo.
- **RF20 (`src/app.py`):** interface local em Streamlit com quatro abas (Acervo e Índice, Solicitações e NLP, Consulta RAG e Revisão, Sentimentos e Métricas), exibindo `"não localizado"` para campos nulos e limpando arquivos temporários de upload em bloco `finally`.
- **RF22 (`src/sentiment.py`):** classificação individual das 12 avaliações fictícias (`positiva`, `negativa`, `neutra`, `indeterminada`), encaminhamento automático para revisão em casos mistos, irônicos ou sem contexto, vedação de inferências psicológicas e agregação determinística em Python com deduplicação por ID e proteção contra lista vazia.
- **RF23 e RF24 (`src/metrics.py`, `src/vector_store.py`):** exclusão de documentos do índice com invalidação de resultados RAG derivados, persistência de decisões humanas (`pendente`, `aprovada`, `rejeitada`, `revisar`) com identificação do operador, regressão das entradas de texto, áudio e OCR do Desafio 1 e matriz consolidada T01–T15.

### Comandos do Desafio 2

CLI de serviços (`src/desafio2_cli.py`):

```bash
python -m src.desafio2_cli demonstrar-schema
python -m src.desafio2_cli indexar --estrategia structural
python -m src.desafio2_cli listar
python -m src.desafio2_cli avaliar-recuperacao
python -m src.desafio2_cli compreender --arquivo dados/originais/solicitacoes/SOL-001_audio_desafio1.txt --id SOL-001
python -m src.desafio2_cli avaliar-solicitacoes
python -m src.desafio2_cli consultar --pergunta "Em quais dias e horários funciona o Núcleo Fictício de Atendimento?"
python -m src.desafio2_cli revisar --execution-id ID_DA_EXECUCAO --decisao revisar --justificativa "Conferir a fonte com a unidade." --operador "servidor_atendimento"
python -m src.desafio2_cli revisar-ficha --id REG-TEXTO --decisao aprovada --justificativa "Dados conferidos." --operador "servidor_atendimento"
python -m src.desafio2_cli avaliar-guardrails
python -m src.desafio2_cli classificar-sentimentos
python -m src.desafio2_cli excluir-documento --documento ACV-ATEND-005 --demonstrar
python -m src.desafio2_cli regressao
python -m src.desafio2_cli avaliar-integrado
```

Interface Streamlit (RF20):

```bash
streamlit run src/app.py
```

### Resultados consolidados do Desafio 2

- **Solicitações (RF14/RF15 — `resultados/avaliacao_nlp_desafio2.json`):** 6/6 categorias corretas, 19/25 campos literais, 25/25 entidades literais após normalização determinística e 6/20 correspondências lexicais diretas nos resumos. Em `SOL-001`, o resumo omitiu a regra de faltas dos primeiros dias; o caso permanece marcado para revisão.
- **Guardrails (RF16 — `resultados/avaliacao_guardrails.json`):** 3/3 ataques adversariais contidos (`ADV-01`, `ADV-02`, `ADV-03`) e 4/4 controles de escopo, tamanho, extensão e limite de chamadas aprovados.
- **Recuperação e RAG (RF17/RF18/RF19 — `resultados/avaliacoes_recuperacao.json`, `resultados/avaliacao_cenarios_rag.json`):** 5/5 acertos no top-3 nas duas estratégias (escolhida `structural`); 8/8 cenários RAG com status correto (5 fundamentadas com citações válidas, 2 abstenções sem chamar geração e 1 conflito detectado). Em `RAG-05`, a resposta omitiu o encaminhamento à coordenação e foi rejeitada na revisão humana.
- **Sentimentos (RF22 — `resultados/avaliacao_sentimentos.json`):** 12/12 avaliações classificadas de acordo com o gabarito (3 positivas, 3 negativas, 3 neutras e 3 indeterminadas encaminhadas para revisão).
- **Exclusão, regressão e matriz T01–T15 (RF23/RF24 — `resultados/matriz_testes_rf23.json`):** remoção de `ACV-ATEND-005` confirmada na busca (2 chunks antes, 0 após exclusão), 3/3 casos de regressão do Desafio 1 processados e 15/15 testes obrigatórios (T01 a T15) aprovados. A suíte automatizada passa com **169 testes** (`python -m unittest discover -s testes -v`).

