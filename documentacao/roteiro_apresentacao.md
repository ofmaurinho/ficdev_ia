# Roteiro de Apresentação — 12 minutos

**Desafio Prático 1 — FIC_DEV | IA Generativa**

> Tempo total: 12 min. Ensaiar antes da apresentação para cumprir os tempos.

---

## Bloco 1 — Contexto e arquitetura (2 min)

**O que apresentar:**
- O problema: central de atendimento institucional com entradas em texto, áudio e imagem.
- Decisão arquitetural central: o sistema opera sem gabarito; o gabarito existe só para avaliação.
- Diagrama rápido: fluxo de dados → extração → minuta → aprovação → TTS/imagem.
- Stack escolhida: OpenAI (LLM, STT, TTS, imagem), Tesseract local, Pillow.

**Pontos de destaque:**
- Separação entre estado do atendimento e estado dos artefatos.
- Aprovação vinculada a hash SHA-256: qualquer alteração invalida a aprovação.

---

## Bloco 2 — Demonstração multimodal ao vivo (6 min)

### 2a. Texto → minuta → aprovação (2 min)
```bash
python -m src.main processar-texto --arquivo arquivos/entrada_texto.txt
python -m src.main prompts --arquivo arquivos/entrada_texto.txt
python -m src.main aprovar-minuta --caso entrada_texto --arquivo-minuta resultados/minutas/minuta_rascunho.txt \
  --operador "equipe" --decisao aprovar --justificativa "Minuta adequada"
```
- Mostrar: dados extraídos, minuta, hash registrado.

### 2b. Áudio → STT → campos críticos (1 min 30 s)
```bash
python -m src.main audio --arquivo arquivos/entrada_audio.mp3 --caso entrada_audio
```
- Mostrar: transcrição bruta, campos com proveniência (origem, método, status).

### 2c. PDF/imagem → OCR → fallback Vision (1 min)
```bash
python -m src.main ocr --arquivo arquivos/entrada_pdf-imagem.pdf --caso entrada_pdf
```
- Mostrar: gatilhos disparados, texto Tesseract vs Vision, aviso de privacidade.

### 2d. TTS + peça visual (1 min 30 s)
```bash
python -m src.main voz --caso entrada_texto --versao 1
python -m src.main imagem --caso entrada_texto
```
- Mostrar: áudio MP3 gerado, nota de proveniência, rótulo "Gerado por IA — conteúdo sintético".

---

## Bloco 3 — Segurança e revisão humana (2 min)

### 3a. Teste de prompt injection (1 min)
```bash
python -m src.main prompts --arquivo arquivos/entrada_texto_injecao.txt
```
- Mostrar: instrução injetada no corpo da mensagem.
- Mostrar: minuta **não** obedeceu à instrução.

```bash
python -m src.main avaliar --modalidade seguranca \
  --gabarito dados/gabaritos/entrada_texto_injecao.json \
  --arquivo resultados/avaliacao_prompts.json --caso injecao
```
- Resultado: `passou` com 0 instruções seguidas.

### 3b. Revisão humana e taxa de aprovação (1 min)
```bash
python -m src.main revisar --prompt B --decisao aprovar --justificativa "Conforme esperado"
python -m src.main avaliar --modalidade stt \
  --gabarito dados/gabaritos/entrada_audio.json \
  --arquivo dados/processados/entrada_audio_transcricao_bruta.txt
```
- Mostrar: WER, campos críticos, pontuação de qualidade.

---

## Bloco 4 — Evidências e encerramento (2 min)

**O que mostrar:**
- `resultados/logs/audit.jsonl` — hashes dos originais, execução, duração, decisões.
- `resultados/revisoes/` — aprovações vinculadas a hash, operador, data.
- `.env.example` sem credenciais, `.gitignore` cobrindo `.env`.
- Gabaritos commitados no Git antes das execuções reais.

**Encerramento:**
- Limitações honestas: amostra pequena, Vision expõe dados, TTS sem verificação automática.
- O que seria diferente em produção: OCR especializado, interface web, base de dados de protocolos.
- `python scripts/verificar_entrega.py` — resultado OK antes de compactar.

---

## Checklist pré-apresentação

- [ ] `.env` com chave válida configurado
- [ ] `python -m unittest discover -s testes -v` — OK
- [ ] `python scripts/verificar_entrega.py` — OK
- [ ] Execuções reais realizadas (STT, OCR, TTS, imagem, prompts, injection)
- [ ] Caso aprovado e caso rejeitado/corrigido registrados
- [ ] Revisão visual da peça registrada
- [ ] Roteiro ensaiado (cronometrar os 12 min)
