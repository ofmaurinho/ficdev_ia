# Relatório de reexecução e validação — Desafio Prático 2

**Data:** 30/10/2026  
**Escopo:** requisitos dos Estudantes 1 e 2 — RF14, RF15, RF17, RF18, RF19 e RF21.

## Execução e método

Os artefatos presentes foram gerados após a limpeza executada pelo operador: as fichas e relatórios trazem horário de 30/10/2026, o Chroma contém as coleções da rodada e há oito consultas RAG identificáveis por hash nos logs. A validação associou cada consulta ao gabarito pelo SHA-256, verificou as fichas e examinou os arquivos de evidência.

Durante esta revisão, não houve chamadas à OpenAI. Foi corrigida a codificação de alguns valores e chaves tipadas no gabarito NLP v2, que continham `?` no lugar de acentos. As seis fichas existentes foram reavaliadas localmente contra o gabarito corrigido. Também foi ajustada a normalização local de entidades para não classificar `Administração` como lugar dentro do nome de um curso, preservar o trecho literal `turno noturno` quando presente e completar `Eixo Tecnológico de Saúde` como entidade `outro`. As fichas foram revalidadas contra os textos originais sem nova geração.

## Resultados por requisito

| Requisito | Resultado observado | Situação |
|---|---|---|
| RF14/RF15 — compreensão e avaliação NLP | Categorias: 6/6. Campos com igualdade literal: 19/25. Fatos do resumo com correspondência lexical: 6/20; essa métrica não reconhece paráfrases. Entidades, após correção local: precisão 25/25 e revocação 25/25, sem tipos divergentes. | Executado; revisão semântica pendente. |
| RF17 — ingestão e índice | `listar` encontrou os seis documentos do manifesto; índice estrutural com 17 chunks. A listagem em processo novo confirmou persistência. Testes locais confirmaram rejeição de caminho fora do acervo, pedido de OCR para PDF sem texto e reindexação idempotente em Chroma temporário (17 chunks após duas indexações; os 17 antigos foram substituídos). | Tecnicamente verificado. |
| RF18 — recuperação | `structural`: 17 chunks e 5/5 hits@3. `fixed_400_overlap_80`: 11 chunks e 5/5 hits@3. Os chunks esperados aparecem nas posições 1, 1, 1, 1 e 3 em ambas. | Empate; sem estratégia vencedora. Revisar relevância dos ranks 2/3. |
| RF19 — cenários RAG | 8/8 estados esperados; 5 fundamentadas, 2 sem evidência e 1 conflito. As cinco respostas fundamentadas citam chunks recuperados; as três abstenções/conflito não chamaram geração. | Estados e citações passaram; qualidade semântica ainda requer revisão. |
| RF21 — provedor e auditoria | OpenAI foi o provedor registrado nas chamadas da rodada. `audit.jsonl` tem 29 eventos e `consultas.jsonl` tem 8; ambos são JSONL válido. Varredura não encontrou campos de conteúdo bruto nem padrões de segredo/CPF/e-mail. A suíte inclui falhas simuladas e limite de chamadas. | Auditoria técnica passou. Custo monetário e comparação entre provedores/modelos não foram medidos. |

## Pendências objetivas para revisão

- **SOL-001:** o resumo omite a regra de cancelamento por faltas dos primeiros dias. Confirmar e corrigir o resumo antes de aprovar a ficha. A data escrita por extenso é semanticamente equivalente à data numérica do gabarito; a divergência literal não prova erro factual.
- As métricas literais/lexicais NLP não aprovam nem reprovam equivalência semântica. Revisar as seis fichas contra os TXT, em especial os assuntos de SOL-001/003/004/005 e o campo `pedido` de SOL-006. Todas as fichas seguem em `revisao_humana`; SOL-005 e SOL-006 corretamente não têm minuta.
- **RAG-05:** a resposta lista o balcão e o e-mail, mas omite que a unidade registra e encaminha o pedido à coordenação responsável, exigido pelo gabarito e presente na fonte. Não aprovar essa resposta até ajustar/regerar e revisar.
- **RAG-01:** resposta cobre os fatos esperados; há uma segunda citação sobre acompanhamento por protocolo que não era necessária à pergunta. Conferir alinhamento entre afirmações e citações.
- Nenhuma resposta fundamentada foi aprovada por pessoa revisora; todas permanecem pendentes.

## Verificações executadas

- `python -m pip check`: sem dependências quebradas.
- `python -m compileall -q src testes`: concluído.
- `python -m src.desafio2_cli demonstrar-schema`: os três JSONs sintáticos inválidos para o schema foram rejeitados como esperado.
- `python -m unittest discover -s testes -v`: **157 testes passaram**.
- Verificações locais, sem rede, de bloqueio de caminho, PDF sem camada textual e idempotência do Chroma passaram.
- A chave `.env` não foi lida nem exibida nesta revisão.

## Passagem para o Estudante 3

O Estudante 3 pode iniciar RF16, RF20 e RF22 usando os contratos/serviços atuais. RF17 e RF18 estão prontos para integração técnica. As pendências semânticas listadas para RF14/RF15/RF19 devem permanecer abertas e registradas; não declarar o escopo dos Estudantes 1 e 2 como aprovação humana completa até essas revisões.
