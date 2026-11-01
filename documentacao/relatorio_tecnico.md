# Relatório Técnico — Central Inteligente de Atendimento e Comunicação Institucional

**Equipe:** FIC_DEV — Programador de Sistemas com IA  
**Desafio:** Prático 1 — Inteligência Artificial Generativa  
**Versão:** 1.0 — 2026

---

## 1. Visão geral do protótipo

O protótipo é uma Central Inteligente de Atendimento que processa solicitações fictícias em **texto**, **áudio** e **imagem/PDF**, gerando minutas de resposta institucional, síntese de voz e peças visuais identificadas como conteúdo sintético. Todo o fluxo mantém evidências de validação humana, segurança e uso responsável da IA.

### Componentes implementados

| Componente | Arquivo | Função |
|---|---|---|
| Cliente LLM | `src/llm_client.py` | Chamadas a texto, STT, TTS, Vision e geração de imagem |
| Processamento de texto | `src/text_processing.py` | Extração local de campos e geração de minuta rascunho |
| Campos críticos | `src/campos.py` | Proveniência por campo (origem, método, status) |
| Áudio | `src/audio.py` | STT validado + TTS do roteiro aprovado |
| OCR/Visão | `src/vision.py` | OCR Tesseract local com fallback Vision |
| Geração de imagem | `src/image_generation.py` | Fundo por IA + composição local Pillow |
| Revisão de minutas | `src/review.py` | Versões, hash SHA-256, aprovação humana |
| Roteiro de leitura | `src/roteiro.py` | Geração determinística para o TTS |
| Gabaritos | `src/gabarito.py` | Carregamento e validação de gabaritos humanos |
| Avaliação | `src/evaluation.py` | WER, similaridade, campos, segurança, pontuação |
| Auditoria | `src/audit.py` | Log JSONL, hashes de originais, estados de artefatos |
| CLI | `src/main.py` | 10 subcomandos integrados |

---

## 2. Arquitetura e decisões de design

### 2.1 Princípio central

O sistema opera sem gabarito. O gabarito é exigido somente no comando `avaliar`. Isso separa a arquitetura operacional da exigência acadêmica de avaliação, refletindo como um sistema real funcionaria.

### 2.2 Dois eixos de estado

**Estado do atendimento** (decisão humana):
```
RECEBIDO → PROCESSANDO → PENDENTE_REVISAO → APROVADO | REJEITADO
```

**Estado de cada artefato** (por tipo e versão):
```
NAO_GERADO → GERANDO → GERADO | FALHA
```

Artefatos: `transcricao`, `texto_ocr`, `estruturado`, `minuta` (versionada), `roteiro_leitura`, `audio`, `imagem`.

### 2.3 Aprovação vinculada a hash

Cada versão de minuta e seu roteiro de leitura têm hashes SHA-256 registrados no momento da criação. A aprovação humana é ligada a `(caso, versão, hash_minuta, hash_roteiro)`. Qualquer alteração posterior invalida a aprovação. O TTS só sintetiza um roteiro com aprovação válida.

### 2.4 OCR em dois momentos

1. **Antes do Vision:** sinais locais (confiança de palavra, texto incompleto, ruído) decidem se o Vision é chamado.
2. **Depois do Vision:** comparação campo a campo; divergência → `INCERTO` → confirmação humana.

Ausência de campo nunca bloqueia a minuta; campo incerto em dado crítico sim.

---

## 3. Modelos e parâmetros utilizados

| Tarefa | Modelo | Parâmetros |
|---|---|---|
| Extração e minuta (prompts A/B/C) | `gpt-4o-mini` | temperature=0, max_tokens=1500 |
| Transcrição de áudio (STT) | `gpt-4o-transcribe` | idioma=pt |
| Síntese de voz (TTS) | `gpt-4o-mini-tts` | voz=alloy, instruções de tom institucional |
| OCR (fallback Vision) | `gpt-4o-mini` | max_tokens=2000 por página |
| Geração de imagem | `gpt-image-2.5-flare` | 1024×1024, qualidade=medium |
| Revisão de transcrição/OCR | `gpt-4o-mini` | temperature=0 |

**Escolha do modelo:** `gpt-4o-mini` foi escolhido pelo equilíbrio entre custo e capacidade suficiente para o protótipo. Ver `documentacao/decisoes_tecnicas.md` para a tabela comparativa completa.

---

## 4. Segurança e proteção contra injeção

### Mecanismos implementados

1. **Delimitação de conteúdo externo:** todo texto recebido do cidadão é encapsulado em `<conteudo_externo_nao_confiavel>...</conteudo_externo_nao_confiavel>` antes de ser enviado ao modelo.
2. **Instruções no papel `system`:** o system prompt é separado do conteúdo do usuário.
3. **Minimização:** dados pessoais fictícios são enviados minimizados.
4. **Avaliação automatizada:** `evaluation.avaliar_seguranca` compara a saída com padrões proibidos definidos no gabarito humano.

### Limitações declaradas

- O teste de mock prova que o programa delimita corretamente o conteúdo. Não prova resistência do modelo real.
- Uma amostra de um caso com um modelo não é suficiente para generalizar.
- Injeções sofisticadas (multi-turno, codificação alternativa) não foram testadas.

---

## 5. Privacidade e LGPD

Todos os dados utilizados são **fictícios** (nome, CPF, RG, e-mail, protocolo). Nenhum dado real de cidadão foi processado.

| Princípio LGPD | Implementação |
|---|---|
| Minimização | Texto minimizado antes do envio; dados pessoais não são exibidos em logs |
| Transparência | Aviso exibido quando Vision é usado (envio ao provedor externo) |
| Segurança | Chave de API nunca aparece em log; `.env` no `.gitignore` |
| Rastreabilidade | Hashes dos originais e metadados de cada chamada registrados |
| Responsabilidade | Revisão humana obrigatória antes de qualquer envio |

---

## 6. Custos e uso do provedor

O protótipo registra duração e tokens quando o provedor os retorna, mas não calcula custo monetário. Não há tabela de preços versionada na configuração, e os preços e o consumo variam por modelo, tamanho da entrada/saída e modalidade. Antes de uma execução com cobrança, a equipe deve consultar os preços vigentes e estimar o custo a partir do uso esperado. `processar-texto` é local e não faz chamada ao provedor.

Na reexecução limpa integral de 29/10/2026, prompts A/B/C, STT, OCR/Vision e geração de imagem concluíram. O TTS foi bloqueado pela ausência de aprovação humana válida, conforme esperado pelo controle de fluxo. A avaliação de STT registrou WER 0,0154 e um erro crítico; OCR obteve 70/100 e divergência nos três campos críticos. A imagem foi gerada com `gpt-image-2.5-flare`, com hash de proveniência válido e revisão visual pendente. O log não deve ser interpretado como valor financeiro da execução.

---

## 7. Limitações e trabalho futuro

- **Amostra pequena:** apenas uma entrada por modalidade. Um sistema real exigiria avaliação em centenas de casos.
- **Sem interface web:** CLI em Python. A interface gráfica foi descartada intencionalmente para focar nos requisitos de IA.
- **OCR local limitado:** Tesseract tem desempenho variável. Em produção, usar um serviço de OCR especializado.
- **TTS sem verificação automática:** a escuta humana é a evidência principal. A transcrição de retorno é informativa.
- **Gabaritos pequenos:** três entradas fictícias não representam diversidade de casos reais.

---

## 8. Verificação da entrega

Execute antes de compactar:
```bash
python scripts/verificar_entrega.py
```

Testes automatizados:
```bash
python -m unittest discover -s testes -v
```

---

## 9. Continuidade — Desafio Prático 2

A evolução do protótipo incorpora extração estruturada, guardrails em camadas, busca vetorial com RAG fundamentado, interface Streamlit, análise de sentimentos e trilha completa de revisão e exclusão (RF14 a RF24), mantendo os módulos multimodais do Desafio 1.

### 9.1 Novos componentes

| Componente | Arquivo | Função |
|---|---|---|
| Schemas e regras de negócio | `src/schemas.py` | Contratos `FichaSolicitacao`, `RespostaRAG`, `AnaliseSentimento`, `ResultadoGuardrail` e validação pós-schema |
| Compreensão NLP | `src/nlp.py` | Extração estruturada, resumo (até 100 palavras), classificação, entidades literais e revisão de fichas |
| Guardrails | `src/guardrails.py` | Validação de entrada, recuperação e saída, filtro de dados indevidos e avaliação adversarial |
| Ingestão e chunking | `src/ingestion.py` | Leitura restrita ao manifesto (`manifest.json`), extração de PDF com página e chunkers `structural` e `fixed_400_overlap_80` |
| Índice vetorial | `src/vector_store.py` | ChromaDB persistente (`dados/indice/chroma`), busca cosine (`1 - distância`) e exclusão de documento/derivados |
| Avaliação de recuperação | `src/rag_evaluation.py` | Comparação das duas estratégias nas cinco perguntas respondíveis |
| Serviço RAG | `src/rag.py` | Recuperação, abstenção antes da geração, detecção de conflito, geração com citações e revisão humana |
| Análise de sentimentos | `src/sentiment.py` | Classificação individual de avaliações e agregação determinística em Python |
| Métricas e matriz RF23 | `src/metrics.py` | Verificadores locais (T01, T02, T13), regressão do Desafio 1 (T15) e consolidação da matriz T01–T15 |
| Interface Streamlit | `src/app.py` | Painel local em quatro abas para acervo, solicitações, RAG e sentimentos/métricas |
| CLI do Desafio 2 | `src/desafio2_cli.py` | Comandos de indexação, compreensão, consulta, revisão, guardrails, sentimentos, exclusão e avaliação integrada |

### 9.2 Resultados medidos e limitações

- **RF14 e RF15 (`resultados/avaliacao_nlp_desafio2.json`):** 6/6 categorias corretas, 19/25 campos literais, 25/25 entidades literais após normalização e 6/20 correspondências lexicais diretas nos resumos. Em `SOL-001`, o resumo omitiu a regra de cancelamento por faltas nos primeiros dias; o caso permanece em estado `revisar`.
- **RF16 (`resultados/avaliacao_guardrails.json`):** 3/3 casos adversariais (`ADV-01`, `ADV-02`, `ADV-03`) bloqueados sem exposição de segredos e 4/4 controles de escopo, tamanho, extensão e limite de chamadas (`max_calls_per_run`) validados.
- **RF17, RF18 e RF19 (`resultados/avaliacoes_recuperacao.json`, `resultados/avaliacao_cenarios_rag.json`):** 6 documentos do manifesto indexados sem duplicação na reindexação; 5/5 acertos no top-3 em ambas as estratégias (adotada `structural` por manter seções completas); 8/8 cenários RAG com status correto (5 fundamentadas com citações válidas, 2 abstenções sem geração e 1 conflito detectado). Em `RAG-05`, a resposta omitiu o encaminhamento à coordenação e foi registrada como `rejeitada`. O limiar de similaridade `0.40` foi calibrado nos oito casos fictícios e pode exigir ajuste em acervos maiores.
- **RF22 (`resultados/avaliacao_sentimentos.json`):** 12/12 avaliações classificadas conforme o gabarito (3 positivas, 3 negativas, 3 neutras e 3 indeterminadas marcadas para revisão). A confiança exibida pelo modelo é estimativa não calibrada; contagens e proporções são calculadas em código Python.
- **RF23 e RF24 (`resultados/demonstracao_exclusao_rf24.json`, `resultados/regressao_desafio1_desafio2.json`, `resultados/matriz_testes_rf23.json`):** exclusão de `ACV-ATEND-005` removeu seus 3 chunks do índice e zerou sua presença na busca (2 chunks antes, 0 depois); 3/3 entradas do Desafio 1 (texto, áudio revisado e OCR corrigido) foram reexecutadas no fluxo novo; 15/15 testes obrigatórios (T01 a T15) e 169 testes unitários passaram.

