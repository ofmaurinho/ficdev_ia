# Decisões técnicas

## Arquitetura e escopo

O protótipo separa o processamento local (`src/text_processing.py`), as chamadas ao provedor (`src/llm_client.py`), os textos canônicos dos prompts (`prompts/*.txt`), seu carregador (`src/prompts.py`) e a auditoria (`src/audit.py`). O comando padrão não depende da API. O comando `prompts` executa o experimento remoto A/B/C.

A implementação multimodal completa (áudio, OCR/visão, síntese de voz e geração de imagem) foi realizada na versão v4 do plano, integrando os módulos `audio.py`, `vision.py`, `image_generation.py`, `review.py`, `roteiro.py`, `gabarito.py` e `evaluation.py`.

## Configuração e chamadas

- `config.json` fornece modelo, temperatura, limite de tokens e timeout; `OPENAI_MODEL` permite sobrescrever o modelo.
- A chave é lida de `OPENAI_API_KEY` via `.env`, ignorado pelo Git. `.env.example` não contém credenciais.
- A chamada usa o SDK oficial da OpenAI e envia instruções confiáveis no papel `system`, separadas do conteúdo recebido no papel `user`.
- O conteúdo externo é delimitado e tratado como dado. A entrada da demonstração é minimizada antes do envio.
- O experimento C usa o metaprompt para produzir um prompt e aplica esse resultado à mesma tarefa e entrada dos prompts A e B.

## Seleção de modelo e tradeoffs

| Alternativa | Custo | Privacidade e abertura | Capacidade no projeto | Evidência |
|---|---|---|---|---|
| OpenAI `gpt-4o-mini` | Cobrança depende de tokens; sem cálculo monetário nesta entrega | Serviço hospedado e proprietário; o texto minimizado ainda é enviado ao provedor | Validado no fluxo textual e multimodal | Chamada real executada |
| Modelo hospedado de maior porte | Custo possivelmente maior; não medido | Continua dependendo de provedor externo e licença proprietária | Poderia melhorar qualidade, mas não foi integrado | Não testado |
| Modelo local de pesos abertos | Sem tarifa por chamada, mas requer hardware | Pode manter o texto localmente | Depende de escolher modelo e integrar runtime | Não testado |

`gpt-4o-mini` foi escolhido como baseline reproduzível. Para STT: `gpt-4o-transcribe`. Para TTS: `gpt-4o-mini-tts`. Para imagem: `gpt-image-1`.

## Dados, auditoria e validação

- Extração, classificação e minuta são locais e não alegam ser resultado da API.
- A auditoria JSONL registra identificador, origem, modalidade, modelo, parâmetros, duração, uso de tokens, resultado/erro e revisão humana pendente. A chave e o conteúdo bruto não são registrados no log.
- As saídas do experimento e metadados são armazenados em `resultados/avaliacao_prompts.json`.
- O comando `revisar` permite aprovar, rejeitar ou registrar pedido de nova geração, vinculando a decisão ao identificador original.
- O custo monetário não é calculado: não há tabela de preço versionada. O uso de tokens é mantido para cálculo posterior.

## Ambiente verificado

Python 3.14.7, OpenAI SDK 3.31.0 e python-dotenv 1.2.3. As dependências runtime diretas e transitivas estão fixadas em `requirements.txt` e `requirements.lock`; o ambiente mínimo documentado é Python 3.10.

---

## Decisões multimodais (implementação v4)

### PDF e OCR: pypdfium2 vs PyMuPDF

**Escolha: `pypdfium2` (licença Apache/BSD-like).**

| Biblioteca | Licença | Observação |
|---|---|---|
| `pypdfium2` | Apache 2.0 / BSD | Recomendada para protótipos e uso acadêmico sem restrições |
| `PyMuPDF` | AGPL-3.0 ou comercial | AGPL exige abertura do código derivado; mais restritivo |

### OCR: dois momentos de decisão

1. **Antes do Vision:** sinais locais (confiança Tesseract, texto incompleto, ruído) decidem se o Vision é necessário. O gabarito **nunca** influencia essa decisão.
2. **Depois do Vision:** comparação campo a campo; divergência vira `INCERTO` e exige confirmação humana.

### TTS: roteiro canônico aprovado

O roteiro de leitura é gerado de forma **determinística** (função Python, sem LLM), junto com a minuta. Os dois são aprovados com hash SHA-256. O TTS recebe o roteiro exatamente como aprovado. A `instructions` da API controla apenas entonação.

### Imagem: sob demanda e independente do atendimento

A peça visual pode ser gerada sem minuta aprovada (para fins de demonstração). O texto institucional, brasão e rótulo são sobrepostos localmente com Pillow; a IA gera apenas o fundo ilustrativo.

### Aprovação: vinculada a (caso, versão, hash)

Nenhuma aprovação é sobrescrita. Criar `v2` não altera a vigente automaticamente. O campo `versao_atual` é controlado pelo operador.

### Gabarito: só para avaliação

O gabarito exige `status: VALIDADO_HUMANO`, `elaborado_por` e `data_elaboracao` preenchidos pela equipe. O comando `avaliar` recusa gabaritos pendentes. Os comandos `audio`, `ocr`, `prompts` e `processar-texto` nunca exigem gabarito.
