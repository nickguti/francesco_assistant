# OmniMind (Francesco) — NOTES.md
> Log condiviso tra tutte le chat Antigravity. Aggiorna questa sezione dopo ogni sessione.

---

## 📌 Panoramica Progetto

**Nome:** OmniMind (alias: Francesco)
**Tipo:** Assistente virtuale desktop Windows — ibrido locale/cloud
**Linguaggio:** Python
**UI:** PyQt6 (tema scuro/chiaro)
**AI Backend:** Google Gemini 2.5 Flash (`gemini_client.py`)
**Database:** SQLite (`omnimind_data.db`)
**Entry point:** `main.pyw`

---

## 🗂️ Struttura File (src/)

```
src/
├── main.pyw           # Entry point, orchestrazione, routing comandi, hotkey globale
├── gui.py             # Finestra principale (sidebar, Chat, Impostazioni, Tracker, Log...)
├── tray.py            # System Tray integration
├── wakeword.py        # Ascolto continuo offline (Vosk + sounddevice)
├── stt.py             # Speech-To-Text (SpeechRecognition, Google Speech IT)
├── tts.py             # Text-To-Speech (edge-tts, voci neurali Microsoft)
├── gemini_client.py   # Client Gemini: chat, visione, traduzioni, coach eSports
├── commands.py        # Comandi Windows nativi (regex → azioni di sistema)
├── time_manager.py    # Gestore timer/sveglie multithread (tono 480Hz)
├── database.py        # Interfaccia sqlite3 (chat log + tracker collezioni)
└── config.py          # Caricamento config.json (API keys, impostazioni runtime)
```

---

## ⚙️ Stack Tecnologico

| Componente       | Tecnologia                          |
|-----------------|-------------------------------------|
| GUI             | PyQt6                               |
| Wake-word       | Vosk (offline) + sounddevice        |
| STT             | SpeechRecognition (Google Speech IT)|
| TTS             | edge-tts / ElevenLabs / OpenAI      |
| AI              | Google Gemini 2.5 Flash SDK         |
| Database        | SQLite3                             |
| System Tray     | QSystemTrayIcon (PyQt6)             |
| Automazione OS  | subprocess, PowerShell, WMI         |
| Spotify         | Spotify Web API                     |
| GPU Monitoring  | nvidia-smi                          |

---

## 🔄 Flusso di Funzionamento

```
AVVIO → diagnostica HW → carica Vosk → init GUI → saluto utente
  ↓
IDLE: wakeword.py ascolta in background
  ↓
TRIGGER: wake-word rilevata → registra audio → stt.py trascrive
  ↓
ROUTING (process_query()):
  ├─ match regex → commands.py → azione locale
  └─ no match → gemini_client.py → risposta AI
  ↓
OUTPUT: tts.py → audio | gui.py → log visivo + badge stato
  ↓
RITORNO IDLE
```

---

## 🎭 Profili di Sistema

| Profilo   | Comportamento                                                      |
|----------|--------------------------------------------------------------------|
| Gaming   | Ottimizza RAM, apre launcher, volume alto, Gemini in modalità breve|
| Focus    | Chiude giochi, disattiva TTS, silenzia notifiche                   |
| Notte    | Abbassa luminosità (PowerShell/WMI), riduce volume                 |

---

## 🧩 Funzionalità Principali

- **Visione schermo:** screenshot → Gemini analizza
- **Lettura documenti:** carica TXT/PDF → Gemini riassume
- **SysAdmin Windows:** volume, luminosità, RAM/CPU/GPU, ping server, kill process
- **Automazione:** riordino Download, estrazione ZIP, password generator, To-Do, Tracker collezioni
- **Spotify:** controllo remoto via API
- **Hotkey globale:** `Ctrl+Shift+A` → analisi clipboard con Gemini
- **Timer/Sveglie:** multithread, tono 480Hz autonomo
- **Coach eSports:** prompt dedicato in `gemini_client.py`

---

## 🏗️ Decisioni Architetturali

- **Multithreading:** ascolto wake-word e timer girano su thread separati; comunicano con la GUI tramite `Queue`
- **Asincrono:** TTS supporta interruzione asincrona mid-playback
- **Offline-first:** wake-word e comandi base non richiedono internet
- **Config runtime:** `config.json` gestito da `config.py`, sincronizzato a runtime

---

## 📋 Chat Antigravity — Mappa

| # | Nome Chat              | Scope                                                      |
|---|------------------------|------------------------------------------------------------|
| 1 | 🧠 Core & Routing      | `main.pyw`, `commands.py`, `config.py` — orchestrazione e regex |
| 2 | 🎨 GUI & Tray          | `gui.py`, `tray.py` — interfaccia utente e system tray     |
| 3 | 🎤 Voice Pipeline      | `wakeword.py`, `stt.py`, `tts.py` — pipeline vocale completa |
| 4 | 🤖 Gemini & AI         | `gemini_client.py` — prompt, personalità, visione, coach   |
| 5 | 🗄️ Database & Config   | `database.py`, `config.py` — persistenza e configurazione  |
| 6 | ⏰ Time Manager        | `time_manager.py` — timer, sveglie, tono audio             |
| 7 | 🔧 Project Assistant   | Architettura, decisioni, refactoring, problemi cross-modulo |
| 8 | 🚀 Release Manager     | GitHub, versioning, README, packaging Windows (.exe)        |

---

## 📝 Log Sessioni

### [DATA] — Setup iniziale
- Creata struttura chat Antigravity
- NOTES.md inizializzato
- TODO: aprire tutte le chat e incollare i rispettivi file di partenza

### 19/06/2026 — Database & Config Module
- Refactoring `database.py`: aggiunti `threading.Lock()` e `PRAGMA journal_mode=WAL` per garantire accessi SQLite concorrenti sicuri e zero perdita dati.
- Refactoring `config.py`: implementato `_config_lock` e caching in RAM basato su `mtime` del file `config.json`. Ora `load_config()` e `get_setting()` permettono l'aggiornamento a caldo delle impostazioni senza gravare sul disco e senza riavviare l'app.

---

## ⚠️ Problemi Noti / TODO

- [ ] Da definire: strategia packaging (PyInstaller? cx_Freeze?)
- [ ] Da verificare: compatibilità Vosk model con lingue miste IT/EN
- [x] Da implementare: sistema di aggiornamento config a caldo senza restart
- [ ] Da testare: interruzione TTS asincrona su Windows 11
- [x] Audit completo del codice e correzione dei difetti (18/08/2026)
- [x] Suite di test sul routing dei comandi (`tests/`)
- [ ] Da valutare: spezzare `gui.py` (1700 righe) e `commands.py` in sotto-moduli

---

## 🔑 Note per l'AI (Antigravity)

- Il progetto gira **solo su Windows** — non considerare soluzioni cross-platform
- I thread comunicano **esclusivamente via `Queue`** — non usare variabili globali condivise
- Il file `NOTES.md` va aggiornato dopo ogni sessione significativa
- Ogni modulo ha una responsabilità singola — rispettare la separazione
- La personalità di Francesco è **brillante e ironica** — mantenerla nel system prompt Gemini