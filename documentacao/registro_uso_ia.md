# Registro de uso de IA no desenvolvimento

## Ferramenta e ambiente

- Assistente: GitHub Copilot no Visual Studio Code.
- Modelo e versão exatos do assistente: não expostos pela interface desta sessão; não foram inferidos.
- Ambiente usado para validação: Python 3.14.7, OpenAI SDK 3.31.0 e python-dotenv 1.2.3.
- Uso: planejamento, implementação, revisão do enunciado e documentação. Chamadas de geração A/B/C foram feitas ao modelo OpenAI indicado no artefato de avaliação, não ao assistente de codificação.

## Solicitações relevantes

As solicitações abaixo são sínteses fiéis do trabalho solicitado, não transcrições literais:

1. Inspecionar o repositório e implementar os requisitos dos Estudantes 1 e 2 do desafio prático.
2. Configurar e validar a chamada real à OpenAI após a configuração do `.env`.
3. Executar o projeto e verificar os testes e a integração real.
4. Reabrir o PDF, comparar os requisitos com código e documentação, revisar `requirements.txt` e tornar a execução reproduzível pelo README.

## Sugestões e decisões

- Aceitas: separação em módulos para prompts, cliente OpenAI, processamento textual e auditoria; chave carregada pelo ambiente; testes locais sem depender de chamadas remotas.
- Modificadas após validação: Prompt C passou a ser realmente gerado por metaprompt e aplicado à mesma tarefa; A/B/C passaram a usar esquema estruturado comum, gabarito prévio e verificação automática. Os campos pessoais desnecessários foram removidos antes do envio à API.
- Rejeitadas: tratar uma resposta executada como automaticamente aprovada; declarar cálculo de custo sem preço configurado; afirmar que áudio/OCR/imagem estão implementados; manter textos que diziam que nenhuma chamada real ocorreu após a chamada ter sido validada.

## Validação feita

- Testes automatizados: `python -m unittest discover -s testes -v` (18 testes aprovados na última execução).
- Experimento real A/B/C após instalação limpa: execução `59db8502-f564-4dd4-8bb8-690fb4168923` em `resultados/avaliacao_prompts.json`; B e C passaram no gabarito automático; A falhou no uso literal de “não localizado”. A confiança `0` retornada por C exige atenção na revisão.
- Segurança: teste de conteúdo malicioso no processamento local, teste de separação de mensagens `system`/`user`, minimização de identificadores antes do provedor e teste de que logs não registram a chave.
- Revisão humana das respostas: ainda pendente; deve ser registrada por integrante da equipe após examinar a evidência.

## Responsabilidade

A IA auxiliou o desenvolvimento, mas não substitui a compreensão, a revisão e a responsabilidade da equipe. **Declaração da equipe a confirmar antes da entrega:** os integrantes revisaram o código, os resultados, as limitações e as decisões registradas e assumem responsabilidade pelo material final.
