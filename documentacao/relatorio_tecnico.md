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

Esta versão acrescenta serviços de extração estruturada/NLP (RF14/15) e ingestão, chunking, Chroma persistente, avaliação de recuperação e RAG configurável/auditado (RF17/18/19/21), sem substituir os fluxos do Desafio 1. O estado por requisito, contratos para Streamlit e pendências do Estudante 3 estão em `documentacao/CONTINUIDADE_ESTUDANTE_3.md`.

O acervo fictício contém seis documentos listados em `dados/originais/acervo/manifest.json`; arquivos de aulas, desafios e editais em `arquivos/` não são incluídos automaticamente. As solicitações, gabaritos e casos adversariais do Desafio 2 estão em seus diretórios dedicados. A indexação usa PyMuPDF para PDFs com camada textual e ChromaDB persistente, com embeddings calculados explicitamente pela OpenAI. O índice não foi populado nesta etapa.

Validação não paga: módulos foram carregados para a demonstração do schema; o CLI demonstrou três casos de JSON válido recusados pelo schema, e a extração local gerou 17 chunks estruturais e 11 fixos. Não foram chamadas APIs, criados embeddings, executadas consultas, medidas taxas/latências/custos ou adicionados arquivos de teste. A disponibilidade e as permissões de `gpt-4o-mini`/`text-embedding-3-small` devem ser verificadas após a configuração manual de `OPENAI_API_KEY`.
