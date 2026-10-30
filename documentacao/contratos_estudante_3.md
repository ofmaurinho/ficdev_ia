# Implementações multimodais — Estudante 3

Este documento registra os módulos multimodais existentes no código. As rotas dependentes da OpenAI exigem `OPENAI_API_KEY`; o processamento de OCR local usa Tesseract e idioma português.

## Áudio — `src/audio.py`

- Valida extensão e tamanho do arquivo antes de chamar STT.
- Preserva transcrição bruta e revisada em artefatos separados.
- Registra idioma, modelo, duração e proveniência dos campos críticos.
- Compara a transcrição com gabarito por WER e campos críticos.
- Gera TTS somente para roteiro canônico ligado por hash a uma aprovação humana válida.
- A escuta humana permanece necessária; a transcrição de retorno é apenas indicial.

## OCR e visão — `src/vision.py`

- Preserva PDF/imagem original e registra hash.
- Executa OCR local com Tesseract primeiro; sinais de baixa confiança podem acionar Vision.
- Mantém texto bruto, resultado Vision e correção em saídas separadas.
- Divergência em campo crítico bloqueia a geração da minuta até confirmação humana.
- `--forcar-vision` existe para demonstração e avaliação. O conteúdo da página é enviado ao provedor externo.

## Imagem — `src/image_generation.py`

- Gera fundo ilustrativo por API e compõe localmente título, orientação, brasão e rótulo de conteúdo sintético.
- Salva prompt, modelo, parâmetros e nota de proveniência.
- A imagem só deve ser marcada como utilizável após inspeção visual humana registrada por `--revisar-visual`.

## Limites da verificação

Os testes automatizados cobrem os fluxos com cliente simulado; a execução limpa com API real depende de disponibilidade, permissões e cota do provedor. Uma chamada que falha não conta como evidência de geração bem-sucedida. Consulte a tabela de RF no README para o estado da última execução real e os casos que ainda requerem revisão.
