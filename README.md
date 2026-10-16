# Central Inteligente de Atendimento e Comunicação Institucional

## Objetivo

Este projeto implementa a etapa inicial do desafio prático de inteligência artificial generativa, com foco em:

- processamento textual de solicitações institucionais;
- classificação, registro e validação local;
- preparação de minutas institucionais sem automatizar envio real;
- auditoria e rastreabilidade das execuções;
- comparativo de prompts A, B e C documentado para uso acadêmico.

## Escopo e status

Este repositório implementa o escopo textual dos Estudantes 1 e 2: experimento de prompts A/B/C, chamada configurável à OpenAI, extração e classificação local, minuta em rascunho, minimização antes do envio externo, revisão humana por CLI e auditoria JSONL. A execução de `processar-texto` é local; somente o comando `prompts` faz chamadas à API.

Áudio, síntese de voz, OCR/visão e geração de imagem não estão implementados. Os módulos `src/audio.py`, `src/vision.py` e `src/image_generation.py` são contratos reservados ao Estudante 3. O pedido de nova geração é registrado para auditoria, mas a chamada subsequente deve ser iniciada pelo operador. Portanto, esta entrega ainda não atende ao produto multimodal completo do desafio.

### Cobertura dos requisitos relacionados aos Estudantes 1 e 2

| Requisito | Estado nesta entrega |
|---|---|
| RF01 | Entrada reproduzível; `config.json` controla caminhos e parâmetros; instruções verificadas em ambiente limpo. |
| RF02 | Experimento A/B/C real, saídas e matriz registrados; B e C passaram a validação automática desta rodada, mas aguardam aprovação humana. |
| RF03 | Instruções `system` separadas do texto `user`, delimitadores, regra “não localizado” e teste de prompt injection. |
| RF04 | Chamada real, timeout, erros mapeados e uso de tokens auditado; custo não calculado sem tabela de preços. |
| RF05 | Extração local para JSON válido, categorias documentadas, campos ausentes e revisão obrigatória. |
| RF11 | Eventos JSONL ligados à execução, com modelo, parâmetros, duração, uso, erros e decisão humana quando registrada. |
| RF12 | Dados fictícios, análise de finalidade/risco e minimização antes do provedor; há risco residual por uso de padrões textuais. |
| RF13 | Gabarito, protocolo de avaliação, taxa automática e comando de revisão disponíveis; a demonstração de aprovação/rejeição humana ainda depende da equipe. |

## Responsabilidades dos estudantes

- Estudante 1: prompts, avaliação e documentação.
- Estudante 2: integração, segurança, texto, classificação e auditoria.
- Estudante 3: multimodal, áudio, OCR, visão e imagens.

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
- Internet e uma chave válida da OpenAI apenas para executar o experimento real de prompts.
- As dependências de runtime, inclusive transitivas, estão fixadas em `requirements.txt`.

## Instalação

PowerShell (Windows):

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Se a política de execução do PowerShell bloquear a ativação, use o Prompt de Comando:

```bat
py -3 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
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

Em uma cópia limpa do projeto, siga as instruções de criação do ambiente e instalação acima, execute os testes e depois `python -m src.main processar-texto`. Essa sequência foi verificada em um ambiente virtual temporário, sem `.env` nem artefatos prévios. Ela gera o JSON estruturado e a minuta local sem chamar a API. Para reproduzir o experimento A/B/C, configure sua própria chave e execute `python -m src.main prompts`; essa etapa depende de internet, disponibilidade/modelo do provedor e pode gerar cobrança. O artefato registra modelo, parâmetros, respostas, tokens quando disponíveis e tempos, mas não fixa preço monetário nem comportamento futuro do serviço.

## Modelos e parâmetros

- Provedor: OpenAI Responses API.
- Modelo: `OPENAI_MODEL`, com fallback para `config.json` (`gpt-4o-mini` no exemplo).
- Temperatura, `max_output_tokens` e timeout vêm de `config.json`.
- Versões verificadas: OpenAI SDK 3.31.0 e python-dotenv 1.2.3; `requirements.txt` fixa também as dependências transitivas instaladas no ambiente validado.
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
- Módulos multimodais permanecem reservados ao Estudante 3.
- O projeto é acadêmico e não substitui revisão humana nem conformidade jurídica completa.

## Segurança e privacidade

- O conteúdo recebido é tratado como não confiável.
- Chaves e segredos não são registrados nos logs.
- Os dados no repositório são fictícios, conforme o desafio.
- O protótipo não deve ser usado para ações institucionais reais.

## Privacidade e limites

Use somente dados fictícios. O processamento local preserva o texto de entrada no JSON estruturado; antes das chamadas à API, o projeto remove data/local de nascimento e campos adicionais com CPF, RG, nome da mãe e e-mail. Nome do solicitante, protocolo e data do atendimento permanecem porque são necessários ao cenário e devem ser fictícios. Logs não armazenam texto bruto nem chave.

O sistema não envia respostas automaticamente. As saídas são rascunhos e precisam de conferência humana. A revisão só muda de pendente quando um operador registra explicitamente a decisão. A solução não substitui avaliação de segurança, jurídica ou de conformidade LGPD.
