# Assistente Virtuale Advanced "Francesco"

Francesco è un assistente virtuale desktop avanzato per Windows sviluppato in Python. Esegue continuamente l'ascolto in background alla ricerca della wake-word "Francesco", interagisce con l'utente tramite messaggi vocali e scritti, supporta comandi locali di automazione e si integra perfettamente nella System Tray di Windows.

## Caratteristiche
- **System Tray Integration**: Funziona silente nella barra delle applicazioni, minimizzabile a icona.
- **Wake-word locale**: Attivazione vocale offline tramite la parola "Francesco" usando `vosk` e `sounddevice`.
- **Speech-to-Text (STT)**: Riconoscimento vocale immediato dei comandi dell'utente.
- **Text-to-Speech (TTS) Premium**: Sintesi vocale naturale e fluida tramite `edge-tts` (voce "it-IT-GiuseppeNeural") con supporto per l'interruzione asincrona del parlato.
- **Parser di Comandi Locali**: Esecuzione rapida di comandi specifici (es. Spotify, YouTube, ora corrente, apertura browser, spegnimento del computer).
- **Gemini Fallback**: Risposte intelligenti fornite dal modello Gemini 1.5 Flash se il comando non è mappato localmente.
- **GUI Moderna**: Interfaccia stile Dark Mode (simile a Discord/ChatGPT) creata con `customtkinter` ed indicatore di stato visivo.

## Requisiti e Installazione

1. Clona o copia questa cartella sul computer.
2. Installa le dipendenze Python:
   ```bash
   pip install -r requirements.txt
   ```
3. Copia il file `.env.example` come `.env` e inserisci la tua chiave API di Gemini (`GEMINI_API_KEY`):
   ```bash
   copy .env.example .env
   ```
4. Avvia l'applicazione:
   ```bash
   python src/main.py
   ```

*Nota: Al primo avvio, l'applicazione scaricherà automaticamente il modello di riconoscimento vocale italiano Vosk (circa 45MB) all'interno della directory `src/model`.*
