# OmniMind — Assistente vocale desktop per Windows

Assistente vocale in Python per Windows. Resta in ascolto in background, si attiva
con una wake-word pronunciata a voce, esegue comandi locali di automazione e passa
a Google Gemini per tutto il resto. Vive nella System Tray.

> Il nome della wake-word è configurabile: il default nel codice è `omnimind`,
> ma il progetto nasce con l'alias "Francesco".

## Caratteristiche

**Voce**
- Wake-word offline con [Vosk](https://alphacephei.com/vosk/) e `sounddevice` — nessun audio lascia il PC finché non pronunci la parola di attivazione
- Trascrizione del comando tramite Google Speech (`SpeechRecognition`)
- Sintesi vocale con tre motori selezionabili: **Microsoft Edge** (gratuito, default), **ElevenLabs**, **OpenAI**
- Interruzione immediata del parlato

**Comandi locali** — architettura a plugin, ognuno con la propria priorità di dispatch:

| Plugin | Cosa fa |
|---|---|
| Produttività e Utilità | ora, data, timer, sveglie, meteo, to-do list, notizie |
| Multimedia & Spotify | play/pausa, traccia successiva, riproduzione via API Spotify |
| Gaming & eSports | avvio lobby, stato dei server, macro Discord, consigli di gioco |
| Intelligenza Artificiale | automazione RPA, visione dello schermo, riassunto documenti, traduzione, analisi appunti |
| Controllo Sistema | volume, luminosità, spegnimento, terminazione processi, profili, diagnostica hardware |
| Lanciatore di App e Web | avvio programmi, ricerche su Google e YouTube |

**Profili di sistema** — Gaming, Focus/Studio, Notte/Relax: ognuno regola volume,
luminosità, notifiche, piano energetico e il tono delle risposte. Attivabili a
voce, dalla GUI o da trigger automatici (a un certo orario, o all'avvio di una
determinata applicazione).

**Interfaccia** — PyQt6, tema scuro o chiaro con colore d'accento configurabile:
chat, impostazioni, gestore profili, guida comandi, log, dashboard hardware in
tempo reale (CPU, RAM, dischi, GPU, rete) e gestione plugin.

## Requisiti

- Windows 10 o 11
- Python 3.11 o superiore
- Microfono
- Una chiave API di Google Gemini ([console](https://aistudio.google.com/apikey))

## Installazione

```bash
pip install -r requirements.txt
```

Copia `.env.example` in `.env` e inserisci la tua chiave:

```bash
copy .env.example .env
```

Avvia:

```bash
pythonw src/main.pyw
```

Oppure con un doppio clic su `Avvia_OmniMind.bat`.

Al primo avvio viene scaricato automaticamente il modello vocale italiano di
Vosk (circa 45 MB) in `src/model`.

## Configurazione

Tutto è modificabile dalla GUI e viene salvato in `config.json` (escluso dal
versionamento, come `.env` e il database).

Alcune impostazioni meritano una nota:

- **Safe mode** — se attiva, spegnimento, riavvio, svuotamento del cestino,
  terminazione processi, riordino dei Download e automazioni RPA chiedono una
  conferma esplicita prima di procedere.
- **Hotkey analisi appunti** — disattivata per default. Se la imposti (es.
  `<ctrl>+<shift>+a`), quella combinazione invia il contenuto degli appunti a
  Gemini: attivala solo se ti sta bene.
- **Soglia rumore microfono** — alzala se in ambiente rumoroso la registrazione
  del comando non si chiude da sola.
- **Visione dello schermo** — cattura il solo monitor attivo. `vision_tutti_schermi`
  in `config.json` estende la cattura a tutti gli schermi.

## Test

```bash
python -m pytest tests/ -q
```

I test coprono il routing dei comandi verso i plugin e l'estrazione dei
parametri. Interrogano soltanto `can_handle()`: non eseguono mai i comandi,
quindi si possono lanciare senza rischio di spegnere il PC o chiudere processi.

## Struttura

```
src/
├── main.pyw           # Orchestratore: code, thread, routing dei trigger
├── gui.py             # Interfaccia PyQt6
├── tray.py            # Icona nella System Tray
├── wakeword.py        # Ascolto continuo offline (Vosk)
├── stt.py             # Trascrizione del comando
├── tts.py             # Sintesi vocale (Edge / ElevenLabs / OpenAI)
├── gemini_client.py   # Client Gemini: chat, visione, documenti, traduzione
├── commands.py        # Funzioni di sistema Windows
├── safety.py          # Conferma delle azioni irreversibili
├── time_manager.py    # Timer e sveglie (persistenti su SQLite)
├── context_monitor.py # Appunti, telemetria, media, trigger automatici
├── database.py        # SQLite: cronologia, timer, sveglie
├── config.py          # Configurazione con cache su mtime
├── utils.py           # Download del modello Vosk, helper vari
└── plugins/           # Un modulo per famiglia di comandi
```

## Limiti noti

- Solo Windows: usa API Win32, `pycaw`, `winsound`, WMI e PowerShell.
- La trascrizione del comando e le risposte richiedono connessione. Wake-word e
  comandi di sistema funzionano offline.
- La dashboard legge la GPU tramite `nvidia-smi`: su schede AMD o Intel quella
  sezione resta vuota.
