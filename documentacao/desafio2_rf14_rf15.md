# Desafio 2 — RF14 e RF15

## Contrato

`src/schemas.py` define `FichaSolicitacao` (`solicitacao.v1`) com protocolo, data, solicitante, assunto, pedido, categoria fechada, resumo, entidades literais, inferências, campos ausentes e revisão. O modelo usa Pydantic v2, propriedades extras proibidas e strings/tipos estritos. Campos possivelmente ausentes são anuláveis, mas continuam propriedades obrigatórias do JSON estruturado.

`validar_ficha()` verifica regras além do schema: a data precisa existir no calendário e estar no texto de origem; protocolo/solicitante e entidades literais precisam de suporte no original; campos nulos devem aparecer em `campos_ausentes`; o resumo limita-se a 100 palavras; lacunas críticas exigem revisão. Essas regras não são garantidas apenas pelo formato JSON. A minuta não é criada quando a validação ou regra de negócio falha ou há campo crítico ausente.

## JSON sintático versus schema

O comando local `python -m src.desafio2_cli demonstrar-schema` demonstra três objetos JSON sintaticamente válidos que não passam no schema: chave extra, tipo incorreto no protocolo e propriedade obrigatória ausente. Na verificação local desta evolução, os três casos foram reconhecidos como JSON válido e rejeitados pelo schema, respectivamente como `extra_forbidden`, `string_type` e `missing`. Essa demonstração não usa API nem mede qualidade de extração.

## NLP e gabaritos

`src/nlp.py` mantém tarefas de compreensão em serviço independente da interface. `processar_solicitacao()` usa `Responses.parse` com `FichaSolicitacao`, recusa vazia/incompleta e no máximo uma repetição transitória conforme config. Antes do envio reaproveita `minimize_text_for_provider()` do Desafio 1. A função local `avaliar_ficha()` compara campos, categoria, fatos essenciais, entidades omitidas/não gabaritadas e deixa fidelidade semântica e afirmações sem suporte explicitamente pendentes de revisão. `avaliar_conjunto_solicitacoes()` processa os seis arquivos do gabarito e grava resultados somente quando executada pelo operador com chave.

O gabarito manual está em `dados/gabaritos/desafio2_solicitacoes.json`: quatro casos completos, um incompleto e um ambíguo. O primeiro reaproveita a transcrição revisada fictícia do Desafio 1. A saída OCR herdada tem divergências/ilegibilidade; ela pode ser encaminhada via `dados/processados/entrada_pdf_ocr_corrigido.txt`, mas não foi usada como verdade de gabarito. A rodada final usou `compreensao_solicitacao.v2` e está registrada em `resultados/avaliacao_nlp_desafio2.json`; foram avaliados 6/6 casos, com categoria 4/6, campos literais 19/24, correspondência lexical de fatos do resumo 6/20 e revocação literal de entidades 10/25. A rodada imediatamente anterior está em `resultados/avaliacao_nlp_desafio2_rodada_2.json` e a primeira em `resultados/avaliacao_nlp_desafio2_rodada_1.json`. A comparação de resumo é lexical, não semântica; as fichas continuam em revisão humana e os índices baixos/erros estão visíveis em vez de aprovados automaticamente.

## Adendo — estado das correções em 30/10/2026

Este documento também registra resultados da implementação inicial. As versões vigentes são prompt `compreensao_solicitacao.v3` e schema `solicitacao.v2`, configurados em `config.json`; o gabarito de solicitações também está na versão v2. Os relatórios e JSONs de ficha existentes não foram regenerados: suas métricas são históricas e não representam validação contra o gabarito atual. Consulte `revisao_manual_desafio2_estudantes_1_2.md` para o roteiro de revisão e `analise_rf18_relevancia.md` para a análise offline do benchmark de recuperação.

O schema atual aceita entidades tipadas como `turno`, `carga_horaria` e `atividade`; a extração local completa entidades literais apoiadas pelo texto sem reenviar dados minimizados ao provedor. Novos artefatos NLP não persistem o texto original da solicitação. Logs passam pela sanitização central. A auditoria informa provedor/modelo, versões de prompt/schema, chamadas, duração, uso retornado e estado de revisão; custo monetário não é calculado.
