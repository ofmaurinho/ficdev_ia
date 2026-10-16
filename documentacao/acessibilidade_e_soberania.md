# Acessibilidade e Soberania de Dados

**Desafio Prático 1 — FIC_DEV | IA Generativa**

---

## 1. Acessibilidade (RF09)

### 1.1 Recurso de acessibilidade em áudio

O protótipo gera um arquivo de áudio MP3 da resposta institucional como recurso de acessibilidade, atendendo a cidadãos com baixa literacia, deficiência visual ou dificuldade de leitura.

**Fluxo:**
1. A minuta é revisada e aprovada por um operador humano.
2. O sistema gera o roteiro de leitura de forma **determinística** (sem LLM), a partir da minuta aprovada.
3. O operador revisa o roteiro junto com a minuta.
4. Ambos são aprovados com hash SHA-256.
5. O TTS sintetiza o áudio a partir do roteiro aprovado, sem nenhuma modificação posterior.
6. O operador ouve o áudio e registra a escuta.

**Garantias:**
- O texto enviado ao TTS é **idêntico** ao roteiro aprovado (verificado por hash).
- A voz não inventa nem omite informações.
- Instruções de entonação controlam somente o ritmo e o tom, não o conteúdo.

**Parâmetros de síntese:**
- Modelo: `gpt-4o-mini-tts`
- Voz: `alloy` (neutra e clara)
- Instruções: "Fale em português do Brasil, em tom institucional: claro, calmo e cordial, em ritmo pausado. Leia números, datas e protocolos devagar."

### 1.2 Limitações declaradas

- A transcrição de retorno (speech-to-text do áudio gerado) é usada apenas como **indício adicional**, rotulada como automática e falível.
- A escuta humana é a evidência principal de qualidade.
- O áudio não inclui descrição de contexto visual (sem audiodescrição de imagens).

---

## 2. Soberania de Dados (RF08)

### 2.1 Princípio

Nenhum dado é enviado ao provedor externo sem necessidade técnica demonstrada. O processamento local é sempre preferido.

### 2.2 Mapa de fluxo de dados por rota

| Rota | Dado enviado ao provedor | Rota 100% local |
|---|---|---|
| `processar-texto` | Nenhum | ✅ Sim |
| `prompts` | Texto minimizado da solicitação | ❌ Não (LLM necessário) |
| `audio` (STT) | Arquivo de áudio | ❌ Não (STT necessário) |
| `audio` (revisão) | Transcrição bruta | ❌ Não (LLM opcional) |
| `ocr` (Tesseract) | Nenhum | ✅ Sim |
| `ocr` (Vision fallback) | Imagem da página | ❌ Não (gatilho técnico) |
| `voz` (TTS) | Roteiro de leitura | ❌ Não (TTS necessário) |
| `imagem` | Prompt estruturado | ❌ Não (geração necessária) |

### 2.3 OCR: decisão antes do Vision

O Vision é chamado somente se sinais locais da extração Tesseract indicarem risco:
- Proporção de palavras com baixa confiança acima de 25%.
- Texto total abaixo do mínimo esperado para o tamanho do documento.
- Ruído excessivo de caracteres.
- Padrão de protocolo ou data parcialmente encontrado mas inválido.

O log registra quais gatilhos dispararam e se o Vision foi efetivamente chamado.

**Aviso exibido ao operador quando o Vision é usado:**
> "Vision envia a página ao provedor externo; usado só com gatilho de risco. Para dados reais, preferir processamento local por soberania e privacidade."

### 2.4 Minimização de dados

Antes de enviar texto ao LLM, o módulo `text_processing.minimize_text_for_provider` remove espaços redundantes, linhas vazias e formata o texto para minimizar o volume enviado.

### 2.5 Dados fictícios

Todos os dados deste protótipo são **estritamente fictícios**:
- Nome: Marcos Vinícius de Almeida Santos / Ana Carolina Ferreira Lima
- CPF: 123.456.789-00 / 987.654.321-00
- E-mail: marcos.almeida.teste@examplo.com / anacarolina.ficdev@exemplo.com
- Protocolo: 2026-000142 / 2026-000199

Nenhum dado pessoal real foi utilizado ou processado.

### 2.6 Chave de API

- Lida de `OPENAI_API_KEY` via `.env`, nunca codificada no fonte.
- O `.env` está no `.gitignore` e nunca é commitado.
- O `.env.example` não contém credenciais.
- A chave não aparece em nenhum log, resultado ou artefato.

---

## 3. Identificação de conteúdo sintético (RF07)

A peça visual gerada por IA exibe obrigatoriamente o rótulo:

> **"Gerado por IA — conteúdo sintético"**

em faixa preta no rodapé da imagem, com texto em amarelo e negrito, visível antes de qualquer uso. A nota de proveniência em JSON documenta:
- Modelo usado, parâmetros e data de geração.
- Elementos sobrepostos localmente (título, texto, brasão, rótulo).
- Status da revisão visual humana.
- Campo `utilizavel: false` até a revisão ser aprovada.
