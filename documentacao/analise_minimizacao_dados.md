# Análise de minimização de dados

## Finalidade, necessidade e risco

| Campo | Finalidade | Necessidade para o protótipo | Risco em cenário real |
|---|---|---|---|
| Protocolo | Relacionar entrada, saída e atendimento | Mantido no caso fictício para extração e rastreabilidade | Pode identificar um atendimento/cidadão |
| Data do atendimento | Contextualizar o pedido e testar extração | Mantida no caso fictício | Pode permitir correlação com outros registros |
| Nome do solicitante | Testar extração do campo obrigatório e personalizar a minuta | Mantido no exemplo fictício; não é necessário para testar todos os prompts | Identifica diretamente uma pessoa |
| Assunto e solicitação | Classificar e preparar minuta | Necessários para a finalidade | Podem conter dados pessoais ou sensíveis não previstos |
| Nascimento e localidade de nascimento | Não usados na decisão nem na classificação | Removidos antes do envio externo | Dados pessoais com risco de identificação |
| CPF, RG, nome da mãe e e-mail | Não usados na tarefa comparativa | O trecho adicional é removido antes do envio externo | Identificadores e contato direto |
| Texto original completo | Preservar evidência de entrada e permitir auditoria local | Mantido somente no JSON processado localmente | Risco de exposição se o artefato for compartilhado |

## Tratamento aplicado

O projeto mantém os materiais de desafio como entradas fictícias e preserva o texto recebido no resultado local para atender ao requisito de extração. `minimize_text_for_provider` remove nascimento/localidade e o bloco de dados pessoais adicionais (CPF, RG, nome da mãe e e-mail) antes da chamada. O nome do solicitante, protocolo, data do atendimento e pedido permanecem na demonstração para permitir comparar extração e redação.

O log JSONL não armazena o texto bruto nem a chave. O artefato JSON do experimento registra o texto minimizado que foi enviado, além do nome do arquivo de origem e das respostas. Não inclua dados reais nos arquivos ou em testes.

## Riscos residuais e limites

- A remoção usa padrões de texto e não substitui detecção robusta de dados pessoais; formatos diferentes podem passar sem remoção.
- O nome, protocolo, data e conteúdo do pedido continuam sendo enviados ao provedor e devem ser exclusivamente fictícios nesta atividade.
- Artefatos processados mantêm o texto original; não devem ser publicados se contiverem dados reais.
- A análise não constitui avaliação jurídica ou certificação de conformidade com a LGPD.
