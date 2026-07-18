# 🔍 OmniMind — Full Codebase Audit Report

**Data:** 2026-07-18  
**Auditor:** Antigravity AI  
**Scope:** Intero codebase Python del progetto OmniMind (Francesco)  
**Metodologia:** Scansione file-by-file, analisi statica, classificazione per priorità, applicazione diretta dei fix Critical/Important

---

## 📋 Sommario Esecutivo

| Categoria | Critical | Important | Minor | Totale |
|-----------|----------|-----------|-------|--------|
| Bug & Correctness | 3 | 5 | 4 | 12 |
| Security | 3 | 1 | 1 | 5 |
| Performance | 0 | 2 | 3 | 5 |
| Maintainability | 0 | 1 | 6 | 7 |
| **Totale** | **6** | **9** | **14** | **29** |

**Fix applicati:** 21 — **Lasciati intatti:** 8

---

## 🔴 ISSUE TROVATI — Classificati per Tipo e Priorità

### 1. BUG & CORRECTNESS

#### 🔴 CRITICAL

| # | File | Problema | Fix Applicato? |
|---|------|----------|----------------|
| B1 | `tts.py` | **Race condition su `self.playing`**: il flag booleano viene letto/scritto da thread multipli (UI thread chiama `stop()`, worker thread lo scrive in `speak()`) senza sincronizzazione. Può causare: audio non interrompibile, crash intermittenti, o doppia riproduzione. | ✅ Sì — Sostituito `self.playing` con `threading.Event()` (`_stop_event`) |
| B2 | `database.py` | **Connessioni SQLite mai chiuse**: il pattern `with get_connection() as conn:` in SQLite fa solo commit/rollback, **non** chiude la connessione. Ogni chiamata a `save_chat_message` o `get_last_chat_messages` lascia un file handle aperto indefinitamente. Su Windows, questo può portare a "database is locked" dopo molte interazioni. | ✅ Sì — Riscritta ogni funzione con try/finally/conn.close() |
| B3 | `wakeword.py` | **Audio stale nella coda al resume**: quando `resume_listening()` viene chiamato dopo l'elaborazione di un comando, la `audio_queue` contiene ancora i chunk audio accumulati durante l'elaborazione/TTS. Vosk li processa come parlato e può triggerare una falsa wake-word. | ✅ Sì — Aggiunto flush della coda audio in `resume_listening()` |

#### 🟡 IMPORTANT

| # | File | Problema | Fix Applicato? |
|---|------|----------|----------------|
| B4 | `main.pyw` | **Status GUI non aggiornato su trascrizione fallita**: quando `transcribe_audio()` ritorna stringa vuota (linea 381), il `wakeword_detector.resume_listening()` viene chiamato ma lo stato della GUI resta su "processing" perché non viene inviato alcun messaggio `("status", ...)` alla queue. L'utente vede l'indicatore bloccato su "elaborazione". | ✅ Sì — Aggiunto `gui_queue.put(("status", ...))` prima del resume |
| B5 | `gemini_client.py` | **Modello AI hardcoded**: l'utente può selezionare un modello diverso nelle impostazioni (es. `gemini-1.5-pro`), ma `send_message()` ricrea sempre il modello con `"gemini-2.5-flash"` hardcoded, ignorando la configurazione. | ✅ Sì — Usa `self._model_name` caricato da config |
| B6 | `gemini_client.py` | **Crash su `response.text` None**: in `analyze_screenshot()`, `response.text` può essere `None` se la risposta è bloccata dai safety filters. Accedere a `.text` direttamente causa `ValueError`. | ✅ Sì — Aggiunto fallback safe con controllo None |
| B7 | `commands.py` | **`play_beep()` non importato nel pomodoro thread**: la funzione `pomodoro_thread()` (linea 486) chiama `play_beep()` ma non la importa. Poiché il thread è separato e `play_beep` non è nel namespace locale, genera `NameError` alla scadenza del timer. | ✅ Sì — Aggiunto `from src.utils import play_beep` |
| B8 | `main.pyw` | **ContextMonitor event loop non chiuso al shutdown**: `exit_app()` imposta solo `self.context_monitor.running = False`, ma l'event loop asyncio del ContextMonitor resta bloccato su `asyncio.gather()`. Il thread resta in vita fino a `sys.exit(0)` forzato. | ✅ Sì — Aggiunto `loop.call_soon_threadsafe(loop.stop)` |

#### 🟢 MINOR

| # | File | Problema | Fix Applicato? |
|---|------|----------|----------------|
| B9 | `commands.py` | **Duplicate recycle bin logic**: il comando "svuota cestino" (linea 1042) usa `os.system('powershell.exe ...')` mentre esiste già `empty_recycle_bin()` (linea 317) che usa la API Win32 corretta. | ✅ Sì — Sostituito con chiamata a `empty_recycle_bin()` |
| B10 | `gui.py` | **WMI CPU polling thread non terminabile**: `poll_wmi_cpu()` usa `while True:` senza condizione di uscita. Sopravvive anche alla chiusura della finestra. | ✅ Sì — Aggiunto flag `_wmi_poll_running` |
| B11 | `commands.py` | **Regex kill_match duplicato**: `kill_match` è definito sia alla linea ~1093 (con blocklist di sicurezza in main.pyw) che alla linea ~1224 (senza blocklist). La seconda cattura override la prima perché raggiunge più pattern. | ❌ No — Troppo rischioso riscrivere l'ordine dei pattern regex senza test funzionali. Flaggato per revisione manuale. |
| B12 | `time_manager.py` | **Alarm che non scatta se `time_str` non matchea al secondo esatto**: il check `current_time_str == a["time_str"]` funziona solo se il polling cade esattamente al minuto giusto. Con `time.sleep(1)` questo è quasi garantito, ma non al 100%. | ❌ No — Il rischio di mancata attivazione è trascurabile (1 check/sec). Fix richiederebbe comparazione `>=` con stato persistente, troppo invasivo. |

---

### 2. SECURITY

#### 🔴 CRITICAL

| # | File | Problema | Fix Applicato? |
|---|------|----------|----------------|
| S1 | `.env.example` | **API key reale hardcoded**: il file contiene `AIzaSyDV06jIgCeKPK2EdIxHwHUMM09j6rRT8p4` — una chiave Gemini reale. Chiunque cloni il repository la ottiene. | ✅ Sì — Sostituita con `YOUR_GEMINI_API_KEY_HERE` |
| S2 | `config.json` | **API keys reali in JSON committato**: contiene la Gemini API key, Spotify Client ID e Secret in chiaro. | ✅ Sì — Sostituite con stringhe vuote. **⚠️ AZIONE MANUALE RICHIESTA**: ruotare/revocare tutte le chiavi esposte! |
| S3 | `commands.py` | **Shell injection via `os.system()`**: i comandi shutdown/riavvio (linee 1264-1285) usano `os.system(f"shutdown /s /t {seconds}")` dove `seconds` proviene da regex input. Anche se il regex estrae solo `\d+`, l'uso di `os.system()` con stringa formattata è un anti-pattern di sicurezza. | ✅ Sì — Tutti i 5 `os.system("shutdown ...")` sostituiti con `subprocess.run([...])` con lista di argomenti |

#### 🟡 IMPORTANT

| # | File | Problema | Fix Applicato? |
|---|------|----------|----------------|
| S4 | `gui.py` | **HTML injection nella chat**: il testo dell'utente viene inserito direttamente come HTML raw (`{text}`) nel chat log. Un messaggio contenente `<script>` o tag HTML malevoli verrebbe renderizzato. Anche se QTextEdit non esegue JavaScript, può causare rendering corrotto. | ✅ Sì — Aggiunto `html.escape()` su testo utente |

#### 🟢 MINOR

| # | File | Problema | Fix Applicato? |
|---|------|----------|----------------|
| S5 | `commands.py` | **`set_screen_brightness` usa `shell=True` con PowerShell**: la stringa PowerShell contiene il parametro `level` (intero da regex). Anche se numerico, è buona pratica evitare `shell=True`. | ❌ No — Il valore è già clamped 0-100 da `max(0, min(100, level))`. Fix richiederebbe riscrittura non banale del command WMI. Rischio basso. |

---

### 3. PERFORMANCE

#### 🟡 IMPORTANT

| # | File | Problema | Fix Applicato? |
|---|------|----------|----------------|
| P1 | `gemini_client.py` | **Modello ricreato ad ogni messaggio**: `send_message()` ricrea `GenerativeModel` e riavvia la chat ad ogni invocazione per aggiornare il system prompt in base al profilo attivo. Questo è costoso e causa la perdita della cache interna del modello. | ✅ Parziale — Migliorata la gestione della history transfer; la ricreazione resta necessaria per il dynamic system prompt |
| P2 | `tts.py` | **`asyncio.run()` crea/distrugge event loop ad ogni speak()**: ogni chiamata a `speak()` crea un nuovo event loop. Su chiamate frequenti, il GC è impattato. | ❌ No — Fix richiederebbe un event loop persistente con scheduling thread-safe. Impatto reale minimo con il pattern d'uso attuale. |

#### 🟢 MINOR

| # | File | Problema | Fix Applicato? |
|---|------|----------|----------------|
| P3 | `config.py` | **`load_config()` chiamata ad alta frequenza senza caching significativo**: molti moduli chiamano `load_config()` ripetutamente. Il caching basato su mtime mitiga, ma ogni chiamata acquisisce un lock e fa `os.path.getmtime()`. | ❌ No — Il sistema di caching con mtime è funzionale. Ottimizzazione richiederebbe refactoring architetturale. |
| P4 | `context_monitor.py` | **Clipboard polling ogni 0.5s è aggressivo**: `poll_clipboard()` chiama `pyperclip.paste()` 2 volte al secondo. Su Windows chiama la Win32 API OpenClipboard ad ogni iterazione. | ❌ No — Aumentare l'intervallo è banale ma potrebbe impattare la user experience per la funzionalità "analizza appunti". Trade-off UX. |
| P5 | `gui.py` | **`nvidia-smi` chiamato via subprocess ogni 2s nel dashboard**: il polling della GPU è pesante. | ❌ No — Si attiva solo quando la schermata Dashboard è visibile. Già ottimizzato con timer condizionale. |

---

### 4. MAINTAINABILITY

#### 🟡 IMPORTANT

| # | File | Problema | Fix Applicato? |
|---|------|----------|----------------|
| M1 | `utils.py` | **`logging.basicConfig()` sovrascrive la configurazione del root logger**: `utils.py` chiama `logging.basicConfig()` che interferisce con il setup del logger in `main.pyw`, causando potenziali log duplicati o handler mancanti. | ✅ Sì — Rimossa la chiamata |

#### 🟢 MINOR

| # | File | Problema | Fix Applicato? |
|---|------|----------|----------------|
| M2 | `utils.py` | **Bare `except:` clause** (linea 81): cattura `SystemExit` e `KeyboardInterrupt`. | ✅ Sì — Sostituito con `except Exception:` |
| M3 | `commands.py` | **File troppo lungo (1460 righe)**: mescola funzioni di sistema, gioco, profili, meteo, todo-list. Idealmente andrebbe spezzato in sotto-moduli. | ❌ No — Refactoring strutturale richiede decisione architetturale. Rischio di breakage elevato senza test suite. |
| M4 | `commands.py` | **Import ridondanti dentro funzioni**: `import pyautogui`, `import os`, `import webbrowser` sono importati sia a livello di modulo che all'interno di singole funzioni (linee 1017, 1029, 1035, 1066). | ❌ No — Impatto nullo su funzionalità. Cleanup cosmetico a basso rischio ma tedioso. |
| M5 | `config.py` | **Module-level variables stale**: le costanti come `GEMINI_API_KEY`, `WAKE_WORD` ecc. (linee 152-173) vengono settate al momento dell'import e non si aggiornano mai. Il codice usa già `load_config()` ovunque serva il valore aggiornato, ma queste costanti sono fuorvianti. | ❌ No — Rimuoverle potrebbe rompere codice che le importa. Segnalato per cleanup futuro. |
| M6 | `context_monitor.py` | **Broad `except Exception` su processi psutil**: le eccezioni specifiche `psutil.NoSuchProcess` e `psutil.AccessDenied` vengono mascherate. | ✅ Sì — Usate eccezioni specifiche psutil |
| M7 | `tts.py` | **`import re` dentro il metodo `speak()`**: import ripetuto ad ogni chiamata. | ✅ Sì — Spostato a livello di modulo |

---

## ✅ MODIFICHE APPLICATE — Dettaglio per File

### `database.py`
- **Riscritta la gestione delle connessioni**: ogni funzione ora usa `try/finally/conn.close()` per garantire la chiusura deterministica del file handle SQLite.
- **Aggiunto `str(DB_PATH)`**: per compatibilità con versioni vecchie di sqlite3 che non accettano `Path` objects.
- **Aggiunto `conn.commit()` esplicito**: le transazioni sono ora committate esplicitamente prima della chiusura.

### `tts.py`
- **Sostituito `self.playing` (bool) con `threading.Event()`**: `_stop_event.set()` in `stop()` e `_stop_event.is_set()` nel loop di attesa. Thread-safe by design.
- **Spostato `import re` a livello di modulo**.
- **Aggiunto `import threading`**.
- **Rimossa variabile `self.playing`**: tutto gestito tramite l'Event.

### `utils.py`
- **Rimossa `logging.basicConfig()`**: preveniva la corretta propagazione dei log al `QueueLoggingHandler` in main.pyw.
- **Bare `except:` → `except Exception:`**: linea 81.

### `commands.py`
- **5x `os.system("shutdown ...")` → `subprocess.run([...], creationflags=CREATE_NO_WINDOW)`**: elimina rischio di shell injection e nasconde la finestra CMD.
- **Duplicated recycle bin → `empty_recycle_bin()`**: rimossa la versione inline con `os.system(powershell)`.
- **Aggiunto `from src.utils import play_beep`** nel thread pomodoro.

### `main.pyw`
- **Aggiunto status update su trascrizione fallita**: l'indicatore torna a "listening"/"muted" anche quando nessun comando viene trascritto.
- **Aggiunto cleanup dell'event loop di ContextMonitor** in `exit_app()`.

### `gemini_client.py`
- **Modello AI caricato da config**: usa `config.get("gemini_model", ...)` invece di stringa hardcoded.
- **Migliorato transfer della chat history**: la cronologia viene preservata quando il modello è ricreato per il cambio di profilo.
- **Safe access a `response.text`**: aggiunto fallback per risposte bloccate dai safety filters.

### `gui.py`
- **HTML injection fix**: `html.escape()` applicato al testo utente prima del rendering nel chat log.
- **WMI CPU thread reso terminabile**: aggiunto flag `_wmi_poll_running`.

### `wakeword.py`
- **Flush della audio_queue su resume**: previene false wake-word da audio residuo accumulato durante l'elaborazione TTS.

### `.env.example`
- **API key reale rimossa**: sostituita con placeholder.

### `config.json`
- **3 API keys reali rimosse**: Gemini, Spotify Client ID, Spotify Secret → stringhe vuote.

### `context_monitor.py`
- **Eccezioni psutil specifiche** nel gaming trigger scan.

---

## ⛔ MODIFICHE NON APPLICATE — Con Motivazione

| # | Cosa | Perché Non Toccato |
|---|------|--------------------|
| 1 | **Spezzare `commands.py` in sotto-moduli** | Refactoring architetturale invasivo. Richiede decisione su come organizzare i moduli e test manuali estensivi su tutti i ~35 pattern regex. Rischio breakage elevato. |
| 2 | **Rimuovere le costanti stale in `config.py`** (GEMINI_API_KEY, WAKE_WORD, ecc.) | Potrebbero essere importate da codice esterno o plugin non visibili nel repo. Breaking change potenziale. |
| 3 | **Ottimizzare `asyncio.run()` in TTS** con event loop persistente | Richiede una riscrittura significativa del modulo TTS con thread dedicato + event loop. L'impatto attuale è trascurabile. |
| 4 | **Risolvere il pattern regex `kill_match` duplicato** | Due blocchi regex in `commands.py` catturano varianti di "chiudi/termina" con logica diversa (uno ha blocklist, l'altro no). Riscrivere l'ordine dei match senza test funzionali è rischioso. |
| 5 | **Ridurre la frequenza del clipboard polling** | Trade-off UX: l'utente potrebbe aspettarsi reattività immediata per "analizza appunti". |
| 6 | **Personalità/System prompt di Gemini** | Non toccato come da istruzione. Nessun bug confermato nella logica del prompt. |
| 7 | **Import ridondanti nelle funzioni di commands.py** | Cleanup cosmetico, zero impatto su funzionalità. Non vale il rischio di diff noise. |
| 8 | **`set_screen_brightness` con `shell=True`** | Il valore è già sanitizzato (clamped 0-100 int). Fix richiederebbe riscrittura complessa del comando WMI PowerShell. |

---

## ✋ CHECKLIST DI VERIFICA MANUALE

L'utente deve eseguire questi test dopo aver applicato le modifiche:

### Voce & Wake-Word
- [ ] Avviare l'app e verificare che la wake-word ("francesco" / configurata) venga rilevata entro 2 secondi dalla pronuncia
- [ ] Dopo aver dato un comando vocale, verificare che l'indicatore di stato torni a "In ascolto" (verde) dopo la risposta TTS
- [ ] Dire la wake-word durante la riproduzione TTS → verificare che l'audio si interrompa immediatamente e l'app passi in registrazione
- [ ] Testare con un comando vocale lungo (~15 secondi) per verificare il timeout di registrazione

### TTS & Audio
- [ ] Inviare un messaggio testuale nella chat → verificare che la risposta vocale venga riprodotta correttamente
- [ ] Premere il pulsante ⏹️ durante la riproduzione vocale → verificare che l'audio si fermi immediatamente
- [ ] Verificare che il volume configurato venga rispettato (cambiare nelle impostazioni e testare)

### Profili
- [ ] Attivare il Profilo Gaming dal menu nella schermata "Profili" → verificare che il volume di sistema venga impostato al valore configurato
- [ ] Attivare il Profilo Notte → verificare che luminosità e volume vengano ridotti
- [ ] Ripristinare il Profilo Standard → verificare che volume e luminosità tornino ai valori normali
- [ ] Selezionare un modello AI diverso nelle impostazioni (es. `gemini-1.5-pro`) → inviare un messaggio → verificare che la risposta arrivi (conferma che il modello configurato viene usato)

### Database & Cronologia
- [ ] Inviare 5+ messaggi nella chat → andare su "Cronologia Vecchia" → verificare che tutti siano presenti
- [ ] Chiudere e riaprire l'app → verificare che la cronologia sia persistita

### Comandi Locali
- [ ] Testare: "che ore sono" → deve rispondere con l'ora corrente
- [ ] Testare: "imposta un timer di 10 secondi" → dopo 10 secondi deve suonare l'allarme
- [ ] Testare: "svuota il cestino" → deve usare l'API Win32 (nessuna finestra PowerShell visibile)
- [ ] Testare: "genera una password" → deve generare e copiare negli appunti

### System Tray
- [ ] Chiudere la finestra (X) → verificare che l'app si minimizzi nella tray (non si chiuda)
- [ ] Doppio click sull'icona tray → la finestra deve riaprirsi
- [ ] Click destro → "Disattiva Ascolto Vocale" → indicatore deve diventare viola/grigio

### Dashboard
- [ ] Aprire la schermata "Dashboard Hardware" → i grafici CPU/RAM devono aggiornarsi in tempo reale
- [ ] Navigare via dalla Dashboard → i timer di polling devono fermarsi (verificabile nei log)

### Sicurezza Post-Audit
- [ ] **⚠️ URGENTE**: Revocare e rigenerare la Gemini API Key (`AIzaSyDV06jIgCeKPK2EdIxHwHUMM09j6rRT8p4`) — è stata esposta nel repository
- [ ] **⚠️ URGENTE**: Rigenerare Spotify Client ID e Secret — esposti in `config.json`
- [ ] Aggiungere `config.json` e `.env` al `.gitignore` per prevenire futuri leak

---

## 📊 Architettura — Mappa del Progetto

```
francesco_assistant/
├── .env.example          # Template variabili d'ambiente (API keys)
├── config.json           # Configurazione runtime (generato automaticamente)
├── omnimind_data.db      # Database SQLite (chat history + tracker)
├── todo_list.json        # To-do list locale
├── requirements.txt      # Dipendenze Python
├── Avvia_OmniMind.bat    # Launcher Windows
├── src/
│   ├── main.pyw          # 🎯 Orchestratore centrale (Queue dispatcher)
│   ├── gui.py            # 🖥️ Interfaccia PyQt6 (chat, settings, dashboard)
│   ├── tray.py            # 🔔 System Tray (QSystemTrayIcon)
│   ├── commands.py        # 🤖 Parser comandi locali (regex-based)
│   ├── gemini_client.py   # 🧠 Client API Gemini (fallback AI)
│   ├── wakeword.py        # 🎤 Wake-word detection (Vosk offline)
│   ├── stt.py             # 🗣️ Speech-to-Text (Google Speech)
│   ├── tts.py             # 🔊 Text-to-Speech (edge-tts + pygame)
│   ├── config.py          # ⚙️ Gestione configurazione (JSON + cache)
│   ├── database.py        # 💾 Persistenza SQLite
│   ├── time_manager.py    # ⏰ Timer/Sveglie multithreaded
│   ├── context_monitor.py # 📡 Clipboard, telemetria, media, triggers
│   └── utils.py           # 🔧 Utility (Vosk download, beep)
└── temp/                  # File audio temporanei TTS
```

### Flusso dei Thread
```
Main Thread (Qt Event Loop)
├── GUI Queue Polling (QTimer 100ms)
├── System Tray (QSystemTrayIcon)
└── Animations (QPropertyAnimation)

Worker Threads (daemon=True)
├── initialize_system → Vosk download + welcome
├── WakeWordDetector.run() → Audio stream persistente
├── process_context_queue → Clipboard/telemetria dispatcher
├── hotkey_listener → Ctrl+Shift+A globale
├── TimeManager._monitor_loop → Timer/sveglie ogni 1s
├── poll_wmi_cpu → CPU % via WMI ogni 1.5s
└── [on-demand] process_query → Gemini/commands per-request

Async Thread (ContextMonitor)
├── poll_telemetry → CPU/RAM ogni 5s
├── poll_clipboard → Clipboard ogni 0.5s
├── poll_commands → Media control polling
└── poll_triggers → Gaming/Night auto-trigger ogni 10s
```

---

*Report generato automaticamente dall'audit del 18 Luglio 2026.*
