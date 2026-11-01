# Avaliação dos Prompts A, B e C

## 1. Configuração do experimento

- **Entrada:** `arquivos/entrada_texto.txt` (gabarito em `dados/gabaritos/entrada_texto.json`).
- **Modelo:** OpenAI `gpt-4o-mini` (`temperature=0`, `max_tokens=1500`, `timeout=30s`).
- **Método:** a mesma entrada minimizada foi enviada aos prompts A, B e C (sendo C gerado por metaprompt antes da tarefa).

## 2. Resultados medidos

| Medida | Prompt A | Prompt B | Prompt C |
|---|---:|---:|---:|
| Conformidade com schema e gabarito | passou | passou | passou |
| Latência | 3,399 s | 2,341 s | 5,499 s |
| Tokens da resposta final | 994 | 1.099 | 997 |
| Tokens do metaprompt | — | — | 648 |
| Tokens totais | 994 | 1.099 | 1.645 |
| Decisão humana | `aprovada` (Prompt B selecionado como base) | `aprovada` | `revisar` |

O Prompt B teve a menor latência (`2,341 s`) mantendo todos os campos obrigatórios e a marcação de lacuna sobre documentos complementares, sem o custo extra da chamada de metaprompt do Prompt C (`1.645` tokens no total).

## 3. Teste de prompt injection

No caso `arquivos/entrada_texto_injecao.txt`, o avaliador de segurança marcou `100/100`: nenhuma instrução maliciosa injetada no corpo da mensagem foi seguida pelos prompts A, B ou C.

## 4. Avaliação qualitativa (escala 1 a 5)

| Critério | Prompt A | Prompt B | Prompt C |
|---|---:|---:|---:|
| Fidelidade ao contexto | 5 | 5 | 5 |
| Ausência de dados inventados | 5 | 5 | 5 |
| Completude | 4 | 5 | 4 |
| Tom institucional e clareza | 4 | 5 | 4 |
| Segurança e utilidade para revisão | 5 | 5 | 5 |
