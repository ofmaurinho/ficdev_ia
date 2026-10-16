# Contratos de integração para o Estudante 3

Os módulos `audio.py`, `vision.py` e `image_generation.py` permanecem com interfaces mínimas, sem implementação funcional.

## Objetivo

- abrir espaço para transcrição, OCR, visão computacional e geração de imagens sem misturar com a lógica de texto e auditoria atual;
- manter classes e funções com nomes claros para integração futura;
- não criar resultados sintéticos que coloquem o projeto em estado enganoso.

## Interfaces previstas

- `audio.transcrever_audio(path: str)`
- `vision.extrair_texto_documento(path: str)`
- `image_generation.gerar_imagem(prompt: str)`

Esses contratos devem ser concluídos somente após a fase inicial do trabalho do Estudante 3.
