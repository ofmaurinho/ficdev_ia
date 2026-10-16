# Decisões técnicas

## Arquitetura e escopo

O protótipo separa o processamento local (`src/text_processing.py`), as chamadas ao provedor (`src/llm_client.py`), os textos canônicos dos prompts (`prompts/*.txt`), seu carregador (`src/prompts.py`) e a auditoria (`src/audit.py`). O comando padrão não depende da API. O comando `prompts` executa o experimento remoto A/B/C.

Áudio, OCR/visão, síntese de voz e geração de imagem permanecem contratos do Estudante 3, não funcionalidades implementadas.

## Configuração e chamadas

- `config.json` fornece modelo, temperatura, limite de tokens e timeout; `OPENAI_MODEL` permite sobrescrever o modelo.
- A chave é lida de `OPENAI_API_KEY` via `.env`, ignorado pelo Git. `.env.example` não contém credenciais.
- A chamada usa o SDK oficial da OpenAI e envia instruções confiáveis no papel `system`, separadas do conteúdo recebido no papel `user`.
- O conteúdo externo é delimitado e tratado como dado. A entrada da demonstração é minimizada antes do envio.
- O experimento C usa o metaprompt para produzir um prompt e aplica esse resultado à mesma tarefa e entrada dos prompts A e B.

## Seleção de modelo e tradeoffs

| Alternativa | Custo | Privacidade e abertura | Capacidade no projeto | Evidência |
|---|---|---|---|---|
| OpenAI `gpt-4o-mini` | Cobrança depende de tokens; sem cálculo monetário nesta entrega | Serviço hospedado e proprietário; o texto minimizado ainda é enviado ao provedor | Validado no fluxo textual; áudio/imagem não estão integrados | Chamada real e experimento A/B/C executados |
| Modelo hospedado de maior porte | Custo possivelmente maior; não medido | Continua dependendo de provedor externo e licença proprietária | Poderia ser avaliado para melhorar qualidade, mas não foi integrado | Não testado |
| Modelo local de pesos abertos | Sem tarifa por chamada, mas requer hardware e operação; custo não medido | Pode manter o texto localmente; pesos acessíveis não significam automaticamente licença open source | Depende de escolher modelo e integrar runtime; não implementado | Não testado |

`gpt-4o-mini` foi escolhido como baseline reproduzível porque a equipe já tinha uma chave OpenAI e foi possível executar o caminho real com o SDK disponível. Isto não constitui benchmark comparativo entre modelos: a execução A/B/C mantém o mesmo modelo para isolar o efeito dos prompts. O comparativo empírico entre modelos, preço vigente e qualidade ainda precisa ser feito se for exigido como evidência separada.

## Dados, auditoria e validação

- Extração, classificação e minuta são locais e não alegam ser resultado da API.
- A auditoria JSONL registra identificador, origem, modalidade, modelo, parâmetros, prompt, duração, uso de tokens quando disponível, resultado/erro e revisão humana pendente. A chave e o conteúdo bruto não são registrados no log.
- As saídas do experimento e metadados são armazenados em `resultados/avaliacao_prompts.json`.
- O comando `revisar` permite aprovar, rejeitar ou registrar pedido de nova geração, vinculando a decisão ao identificador original. A equipe ainda deve tomar as decisões reais; o protótipo nunca envia respostas institucionais.
- O custo monetário não é calculado: não há tabela de preço versionada. O uso de tokens é mantido para cálculo posterior.

## Ambiente verificado

Python 3.14.7, OpenAI SDK 3.31.0 e python-dotenv 1.2.3. As dependências runtime diretas e transitivas estão fixadas em `requirements.txt`; o ambiente mínimo documentado é Python 3.10.
