import os
import sys
import time

# Aggiunge la directory genitore (root del progetto) a sys.path prima di importare i moduli interni
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import queue
import logging
import threading
import webbrowser
import json
import pyautogui
import shutil
import subprocess
from src.config import MODEL_DIR, load_config
from src.utils import ensure_vosk_model, play_beep, costruisci_prompt_dati
from src.wakeword import WakeWordDetector
from src.stt import transcribe_audio
from src.tts import TTSManager
from src.commands import parse_local_command
from src.gemini_client import GeminiClient
from src.gui import AssistantGUI
from src.tray import TrayIconManager
from src.time_manager import TimeManager
from src.database import init_db, save_chat_message, get_last_chat_messages
from src import safety

# Configurazione del Logger principale
LIVELLI_LOG = {"Debug": logging.DEBUG, "Info": logging.INFO, "Error": logging.ERROR}


def _livello_configurato() -> int:
    """Livello di log scelto dall'utente. La chiave era salvata ma mai applicata."""
    try:
        from src.config import get_setting
        return LIVELLI_LOG.get(get_setting("log_level", "Info"), logging.INFO)
    except Exception:
        return logging.INFO


root_logger = logging.getLogger()
root_logger.setLevel(_livello_configurato())

# Rimuovi eventuali handler di default per evitare doppie stampe
for h in list(root_logger.handlers):
    root_logger.removeHandler(h)

_formato = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# Handler per la console
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(_formato)
root_logger.addHandler(console_handler)

# Handler su file con rotazione: finora i log vivevano solo in memoria nella
# schermata Log e sparivano alla chiusura, rendendo non diagnosticabile
# qualunque errore avvenuto in una sessione precedente.
try:
    from logging.handlers import RotatingFileHandler
    from src.config import BASE_DIR

    _log_dir = BASE_DIR / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        _log_dir / "omnimind.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(_formato)
    root_logger.addHandler(file_handler)
except Exception as _e:
    print(f"Impossibile inizializzare il log su file: {_e}")

logger = logging.getLogger("OmniMindMain")

# Risposte accettate nelle macchine a stati di conferma.
RISPOSTE_SI = ("sì", "si", "certo", "dai", "fai pure", "yes", "ok", "confermo", "procedi")
RISPOSTE_NO = ("no", "annulla", "lascia stare", "no grazie", "ferma", "stop")

# Processi che non devono mai essere terminati dal comando "chiudi <nome>".
# pythonw.exe e' il processo con cui gira OmniMind stesso: senza di esso in
# lista, "chiudi python" terminava l'assistente.
PROCESSI_PROTETTI = {
    "explorer.exe", "svchost.exe", "smss.exe", "csrss.exe", "wininit.exe",
    "winlogon.exe", "services.exe", "lsass.exe", "dwm.exe", "ctfmon.exe",
    "sihost.exe", "audiodg.exe", "cmd.exe", "conhost.exe", "system",
    "python.exe", "pythonw.exe", "py.exe",
}

# Combinazioni che una sequenza generata dal modello non puo' premere.
HOTKEY_VIETATE = {
    ("r", "win"), ("alt", "ctrl", "del"), ("alt", "f4"),
    ("ctrl", "esc", "shift"), ("l", "win"), ("win", "x"),
}

INTERVALLI_DIGITAZIONE = {"Lento (Sicuro)": 0.08, "Normale": 0.01, "Fulmineo": 0.0}

MAX_STEP_RPA = 15


class QueueLoggingHandler(logging.Handler):
    """Handler personalizzato che inoltra i record di log formattati alla gui_queue."""
    def __init__(self, gui_queue):
        super().__init__()
        self.gui_queue = gui_queue

    def emit(self, record):
        try:
            log_entry = self.format(record)
            self.gui_queue.put(("log", (record.levelname, log_entry)))
        except Exception:
            self.handleError(record)

class OmniMindAssistant:
    """
    Coordinatore centrale dell'applicazione.
    Gestisce l'interazione tra l'interfaccia grafica (GUI), l'icona della barra
    delle applicazioni (System Tray), lo Shared Audio Stream (ascolto continuo),
    l'esecutore dei comandi ed il client API Gemini.
    """
    def __init__(self):
        self.gui_queue = queue.Queue()
        self.is_muted = False
        self.running = True
        self.model_path = None

        # Variabili di stato per il flusso di conferma di ricerca Google
        self.attesa_conferma_ricerca = False
        self.query_sospesa = ""

        # Conferma delle azioni irreversibili (safe_mode_confirm)
        self.attesa_conferma_azione = False
        self.testo_azione_sospeso = ""

        # Inizializza il database locale SQLite
        init_db()

        # Registra QueueLoggingHandler
        queue_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        self.queue_handler = QueueLoggingHandler(self.gui_queue)
        self.queue_handler.setFormatter(queue_formatter)
        self.queue_handler.setLevel(logging.INFO)
        root_logger.addHandler(self.queue_handler)

        # Inizializza i moduli indipendenti dall'audio/lingua
        self.gemini_client = GeminiClient()
        self.tts_manager = TTSManager()
        self.time_manager = TimeManager(self.gui_queue)
        self.wakeword_detector = None
        self.wakeword_thread = None

        # Inizializza Context & Monitor Module
        from src.context_monitor import ContextMonitor
        self.context_queue = queue.Queue()
        self.context_monitor = ContextMonitor(out_queue=self.context_queue)
        self.context_monitor.start()
        threading.Thread(target=self.process_context_queue, daemon=True).start()

        # Carica configurazione
        self.config_data = load_config()

        # Crea la GUI CustomTkinter con la callback per il salvataggio impostazioni
        self.gui = AssistantGUI(
            gui_queue=self.gui_queue,
            on_send_text_callback=self.handle_text_input,
            on_toggle_mute_callback=self.toggle_mute,
            on_exit_callback=self.exit_app,
            on_settings_saved_callback=self.reload_settings,
            on_stop_tts_callback=self.tts_manager.stop,
            on_state_change_callback=lambda state: self.tray.set_icon_by_state(state) if hasattr(self, 'tray') else None,
            on_new_chat_callback=self.gemini_client.reset_chat
        )

        # Gestione dell'avvio minimizzato
        if self.config_data.get("start_minimized", False):
            self.gui.hide()
            logger.info("Applicazione avviata in modalità minimizzata nella System Tray.")
        else:
            self.gui.show()

        # Crea l'icona nella System Tray
        self.tray = TrayIconManager(
            on_show_callback=self.show_gui,
            on_toggle_mute_callback=self.toggle_mute,
            on_exit_callback=self.exit_app,
            get_mute_status_callback=lambda: self.is_muted
        )
        self.tray.start()

        # Avvia il listener di hotkey globale
        self.start_hotkey_listener()

        # Avvia l'inizializzazione del modello acustico Vosk in un thread separato
        threading.Thread(target=self.initialize_system, daemon=True).start()

    def _ripristina_ascolto(self):
        """Riporta il rilevatore in ascolto della wake-word e aggiorna lo stato."""
        self._ripristina_ascolto()

    def _avvia_azione(self, target, descrizione="operazione"):
        """
        Esegue un'azione asincrona garantendo il ripristino dell'ascolto.

        Senza il finally, qualunque eccezione (o un return anticipato) lasciava
        il WakeWordDetector nello stato 'processing', che nessun ramo della
        macchina a stati gestisce: l'assistente smetteva di rispondere alla
        wake-word fino al riavvio dell'applicazione.
        """
        def runner():
            try:
                target()
            except Exception as e:
                logger.error(f"Errore durante {descrizione}: {e}", exc_info=True)
                msg = f"Non sono riuscito a completare {descrizione}: {e}"
                self.gui_queue.put(("message", ("OmniMind", msg)))
            finally:
                self._ripristina_ascolto()

        threading.Thread(target=runner, daemon=True).start()

    def process_context_queue(self):
        """Dispatcher per i messaggi provenienti da ContextMonitor (Clipboard, Telemetria, Media)."""
        while self.running:
            try:
                msg_type, data = self.context_queue.get(timeout=0.5)

                if msg_type == "clipboard_event":
                    # Il testo copiato arriva qui; non blocchiamo la UI ma informiamo o analizziamo se necessario.
                    # Ad esempio, si potrebbe mandare a log_system o inviare notifiche.
                    logger.info(f"Rilevato nuovo testo nella clipboard ({len(data)} char)")

                elif msg_type == "system_telemetry":
                    # data = {"cpu_percent": ..., "ram_percent": ..., "ram_avail_gb": ...}
                    if data["cpu_percent"] > 95.0:
                        logger.warning(f"Allerta Sistema: Uso CPU al {data['cpu_percent']}%")
                        self.gui_queue.put(("log", ("WARNING", f"Allerta CPU: {data['cpu_percent']}%")))

                elif msg_type == "media_status":
                    if data:
                        logger.info(f"Media Update: '{data['title']}' by {data['artist']} [{data['status']}]")
                        self.gui_queue.put(("log", ("INFO", f"Media in riproduzione: {data['title']} - {data['artist']}")))

                elif msg_type == "automation_trigger":
                    from src.commands import attiva_profilo
                    profilo = data
                    logger.info(f"Trigger Automatico Innescato: {profilo}")
                    success, chat_msg, voice_msg = attiva_profilo(profilo)
                    self.gui_queue.put(("system", f"⚡ Auto-Trigger: {chat_msg}"))
                    if not self.is_muted:
                        self.tts_manager.speak(voice_msg)

            except queue.Empty:
                pass
            except Exception as e:
                logger.error(f"Errore nel dispatcher context_queue: {e}")

    def initialize_system(self):
        """Esegue la diagnostica PC, pronuncia il benvenuto, scarica ed inizializza Vosk."""
        self.gui_queue.put(("status", "downloading"))

        def status_callback(msg):
            self.gui_queue.put(("system", msg))

        try:
            import psutil
            import socket

            # 1. Esegui la diagnostica rapida PC
            cpu = psutil.cpu_percent(interval=0.1)
            ram = psutil.virtual_memory()
            ram_avail = ram.available / (1024**3)
            hardware_line = f"• HARDWARE: CPU {cpu}% | RAM Disponibile: {ram_avail:.2f} GB -> NELLA NORMA"

            t0 = time.perf_counter()
            try:
                s = socket.create_connection(("8.8.8.8", 53), timeout=1.0)
                s.close()
                latency_ms = int((time.perf_counter() - t0) * 1000)
                network_line = f"• RETE: Connessione attiva | Latenza media: {latency_ms} ms"
            except Exception:
                network_line = "• RETE: Offline o Latenza elevata"

            gemini_key = self.config_data.get("gemini_api_key", "")
            if gemini_key and len(gemini_key) >= 30 and gemini_key.startswith("AIzaSy"):
                gemini_line = "• SERVIZI AI: API Gemini configurata (Endpoint v1)"
            else:
                gemini_line = "• SERVIZI AI: API Gemini NON configurata o formato errato"

            wake_word = self.config_data.get("wake_word", "omnimind")
            vocal_line = f"• FLUSSO VOCALE: Wake-Word \"{wake_word}\" -> ATTIVA"

            active_profile = self.config_data.get("active_profile", "Nessuno")
            profile_line = f"• ASSETTO DI SISTEMA: Profilo \"{active_profile}\" caricato."

            report = (
                "[SISTEMA] Inizializzazione OmniMind in corso...\n"
                "--------------------------------------------------\n"
                f"  {hardware_line}\n"
                f"  {network_line}\n"
                f"  {gemini_line}\n"
                f"  {vocal_line}\n"
                f"  {profile_line}\n"
                "--------------------------------------------------\n"
                "Inizializzazione completata. Tutti i moduli sono operativi."
            )

            # Stampa il report in chat log
            self.gui_queue.put(("system_report", report))

            # 2. Messaggio di benvenuto vocale e typewriter
            welcome_msg = "Sistemi caricati con successo. Sono pronto, come posso aiutarti oggi?"
            self.gui_queue.put(("message", ("OmniMind", welcome_msg)))
            save_chat_message("OmniMind", welcome_msg)

            # Riproduce il benvenuto in modalità parlata (asincrona, non blocca Vosk)
            self.tts_manager.speak(welcome_msg)

            # 3. Trova o scarica il modello Vosk ed imposta il percorso
            self.model_path = ensure_vosk_model(status_callback)

            # Avvia lo stream audio persistente
            self.start_wakeword_detector()

            self.gui_queue.put(("system", "Inizializzazione completata. OmniMind è attivo!"))
            logger.info("OmniMind inizializzato con successo e pronto all'ascolto.")

        except Exception as e:
            logger.error(f"Errore durante l'inizializzazione: {e}")
            self.gui_queue.put(("system", "Errore critico durante il caricamento del modulo vocale."))

    def start_wakeword_detector(self):
        """
        Inizializza e avvia il thread del modulo audio a stream condiviso.
        Viene eseguito una sola volta all'avvio dell'applicazione.
        """
        if not self.model_path:
            logger.warning("Impossibile avviare il rilevatore: percorso modello non impostato.")
            return

        logger.info("Avvio dello Shared Audio Stream per la wake-word...")
        self.wakeword_detector = WakeWordDetector(
            self.model_path,
            self.handle_wake_word_detected,
            self.handle_command_recorded,
            self.config_data.get("wake_word", "omnimind")
        )
        self.wakeword_detector.paused = self.is_muted

        self.wakeword_thread = threading.Thread(target=self.wakeword_detector.run, daemon=True)
        self.wakeword_thread.start()

        self.gui_queue.put(("status", "muted" if self.is_muted else "listening"))

    def start_hotkey_listener(self):
        """
        Registra la hotkey globale per l'analisi degli appunti.

        Disattivata per default: la combinazione era fissa (Ctrl+Shift+A, comune
        in molti editor) e inviava gli appunti a un servizio esterno senza
        anteprima. Ora va abilitata esplicitamente dalle impostazioni.
        """
        combinazione = self.config_data.get("hotkey_appunti", "").strip()
        if not combinazione:
            logger.info("Hotkey globale per gli appunti non configurata: listener non avviato.")
            return

        def run_listener():
            try:
                from pynput import keyboard

                def on_activate():
                    logger.info(f"Hotkey globale ({combinazione}) rilevata! Avvio analisi appunti...")
                    self.gui_queue.put(("message", ("Utente", "[Analisi Appunti via Hotkey]")))
                    save_chat_message("Utente", "[Analisi Appunti via Hotkey]")
                    self.process_query("spiegami gli appunti")

                hotkeys = {combinazione: on_activate}

                listener = keyboard.GlobalHotKeys(hotkeys)
                listener.start()
                logger.info(f"Listener hotkey globale ({combinazione}) avviato con successo.")

                # Mantiene in vita il listener
                while self.running:
                    time.sleep(0.5)
            except Exception as e:
                logger.warning(f"Impossibile avviare il listener delle hotkey globali: {e}")

        threading.Thread(target=run_listener, daemon=True).start()

    def reload_settings(self, config_data):
        """Aggiorna ed applica a runtime le nuove impostazioni salvate dall'utente."""
        logger.info("Rilevata modifica delle impostazioni. Applicazione a runtime...")
        self.config_data = config_data

        # 1. Aggiorna chiave API e modello SENZA azzerare la conversazione:
        # _initialize() faceva start_chat(history=[]), quindi salvare una
        # qualsiasi impostazione cancellava il contesto in corso.
        self.gemini_client.aggiorna_credenziali(config_data)

        # 2. Aggiorna voce, volume e credenziali del TTS Manager
        self.tts_manager.update_settings(config_data)

        # 3. Aggiorna la wake-word a runtime
        new_ww = config_data.get("wake_word", "omnimind")
        if self.wakeword_detector:
            self.wakeword_detector.update_wake_word(new_ww)
            # Slider "Soglia Rumore Mic": esisteva in GUI ma la soglia usata
            # dal rilevatore era una costante hardcoded.
            self.wakeword_detector.update_sensitivity(config_data.get("mic_sensitivity", 400))

        # 4. Livello di log
        nuovo_livello = LIVELLI_LOG.get(config_data.get("log_level", "Info"), logging.INFO)
        root_logger.setLevel(nuovo_livello)

        self.gui_queue.put(("system", "Nuove impostazioni applicate con successo."))

    def show_gui(self, icon=None, item=None):
        """Ripristina e visualizza la finestra della chat."""
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self.gui.restore_window)

    def toggle_mute(self, icon=None, item=None):
        """Attiva o disattiva l'ascolto continuo della wake-word."""
        self.is_muted = not self.is_muted
        logger.info(f"Stato ascolto vocale modificato in: {'Silenziato' if self.is_muted else 'Attivo'}")

        if self.wakeword_detector:
            self.wakeword_detector.paused = self.is_muted

        # Aggiorna lo stato visivo dell'indicatore
        state = "muted" if self.is_muted else "listening"
        self.gui_queue.put(("status", state))

        # Aggiorna il bottone nella GUI
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self.gui.update_mute_ui(self.is_muted))

    def handle_text_input(self, text):
        """Gestisce una richiesta testuale inserita direttamente nella chat."""
        # Se OmniMind sta parlando, interrompilo immediatamente
        self.tts_manager.stop()

        # Salva la richiesta dell'utente nel database
        save_chat_message("Utente", text)

        # Esegue la query in background per non bloccare l'interfaccia
        threading.Thread(target=self.process_query, args=(text,), daemon=True).start()

    def handle_wake_word_detected(self):
        """
        Eseguito all'intercettazione della wake-word.
        Non interrompe lo stream audio che rimane aperto, si limita a fermare
        il parlato in corso, aggiornare lo stato ed emettere il bip sonoro.
        """
        logger.info("Wake-word rilevata! Avvio registrazione del comando vocale...")

        # 1. Interrompe l'audio in corso (TTS)
        self.tts_manager.stop()

        # 2. Aggiorna lo stato visivo ed emette il segnale acustico bip
        self.gui_queue.put(("status", "recording"))
        play_beep()

    def handle_command_recorded(self, audio_data):
        """
        Callback eseguita dallo stream unificato quando viene rilevata la fine
        del parlato (silenzio). Lancia la trascrizione in un thread dedicato.
        """
        threading.Thread(target=self._process_recorded_command, args=(audio_data,), daemon=True).start()

    def _process_recorded_command(self, audio_data):
        """Trascrive l'audio accumulato in memoria ed avvia l'elaborazione."""
        self.gui_queue.put(("status", "processing"))

        # Trascrive l'audio pre-acquisito (senza riaprire il microfono)
        command_text = transcribe_audio(audio_data)

        if command_text:
            # Scrive il comando trascritto in chat log e database
            self.gui_queue.put(("message", ("Utente", command_text)))
            save_chat_message("Utente", command_text)
            # Elabora la query
            self.process_query(command_text)
        else:
            logger.info("Nessun comando vocale decifrato.")
            # Ritorna in ascolto della wake-word se non c'è testo valido
            self._ripristina_ascolto()

    def process_query(self, text):
        """Elabora il testo (scritto o trascritto) eseguendo l'automazione o chiamando Gemini."""
        self.gui_queue.put(("status", "processing"))
        text_clean = text.lower().strip()

        is_async_trigger = False

        # ----------------- STATE MACHINE: CONFERMA AZIONE IRREVERSIBILE -----------------
        if self.attesa_conferma_azione:
            self.attesa_conferma_azione = False
            testo_sospeso = self.testo_azione_sospeso
            self.testo_azione_sospeso = ""

            if any(k == text_clean for k in RISPOSTE_SI):
                # La conferma vale solo per questa ri-esecuzione, in questo thread.
                with safety.conferma_concessa():
                    is_async_trigger = self._process_standard_query(testo_sospeso)
            elif any(k == text_clean for k in RISPOSTE_NO):
                resp_text = "Va bene, non faccio nulla."
                self.gui_queue.put(("message", ("OmniMind", resp_text)))
                save_chat_message("OmniMind", resp_text)
                self.gui_queue.put(("status", "speaking"))
                self.tts_manager.speak(resp_text)
            else:
                logger.info("Risposta alla conferma non chiara: annullo ed elaboro come nuova richiesta.")
                self.gui_queue.put(("message", ("OmniMind", "Non ho capito: annullo l'azione per sicurezza.")))
                is_async_trigger = self._process_standard_query(text)

            if not is_async_trigger:
                self._ripristina_ascolto()
            return

        # ----------------- STATE MACHINE: CONFERMA RICERCA GOOGLE -----------------
        if self.attesa_conferma_ricerca:
            self.attesa_conferma_ricerca = False
            query_salvata = self.query_sospesa
            self.query_sospesa = ""

            # Controlla se la risposta dell'utente è un "Sì" o varianti
            if any(k == text_clean for k in RISPOSTE_SI):
                url = f"https://www.google.com/search?q={query_salvata.replace(' ', '+')}"
                webbrowser.open(url)

                resp_text = f"Ricerca Google avviata per: '{query_salvata}'."
                voice_text = f"Cerco {query_salvata} su Google."

                self.gui_queue.put(("message", ("OmniMind", resp_text)))
                save_chat_message("OmniMind", resp_text)
                self.gui_queue.put(("status", "speaking"))
                self.tts_manager.speak(voice_text)
            # Controlla se la risposta dell'utente è un "No" o varianti
            elif any(k == text_clean for k in RISPOSTE_NO):
                resp_text = "Va bene, annullo la ricerca."
                self.gui_queue.put(("message", ("OmniMind", resp_text)))
                save_chat_message("OmniMind", resp_text)
                self.gui_queue.put(("status", "speaking"))
                self.tts_manager.speak(resp_text)
            else:
                logger.info("Risposta a conferma non chiara. Elaboro come nuova richiesta.")
                is_async_trigger = self._process_standard_query(text)
        else:
            is_async_trigger = self._process_standard_query(text)

        # Ripristina l'ascolto vocale offline se non è stato lanciato un trigger asincrono
        if not is_async_trigger:
            self._ripristina_ascolto()

    def _process_standard_query(self, text) -> bool:
        """
        Esegue il parser standard di comandi locali o devia la chiamata su Gemini.
        Ritorna True se il comando ha avviato un'elaborazione asincrona in background.
        """
        is_command, chat_response, voice_response = parse_local_command(text)

        if is_command:
            # 0. Azione sospesa in attesa di conferma esplicita (safe_mode_confirm)
            if chat_response.startswith(safety.PREFISSO):
                domanda = chat_response[len(safety.PREFISSO):]
                self.attesa_conferma_azione = True
                self.testo_azione_sospeso = text
                self.gui_queue.put(("message", ("OmniMind", domanda)))
                save_chat_message("OmniMind", domanda)
                self.gui_queue.put(("status", "speaking"))
                self.tts_manager.speak(voice_response or domanda)
                return False

            # 1. Gestione Sveglie e Timer
            if chat_response.startswith("timer_set:"):
                parts = chat_response.split(":", 2)
                seconds = int(parts[1])
                label = parts[2] if len(parts) > 2 else "Timer"
                self.time_manager.add_timer(seconds, label)
                self.gui_queue.put(("status", "speaking"))
                self.tts_manager.speak("Timer impostato.")
                return False

            elif chat_response.startswith("alarm_set:"):
                parts = chat_response.split(":", 3)
                hh = parts[1]
                mm = parts[2]
                label = parts[3] if len(parts) > 3 else "Sveglia"
                time_str = f"{hh}:{mm}"
                self.time_manager.add_alarm(time_str, label)
                self.gui_queue.put(("status", "speaking"))
                self.tts_manager.speak("Sveglia impostata.")
                return False

            # 2. Visione Schermo (Occhi)
            elif chat_response.startswith("vision_trigger:"):
                prompt = chat_response.split(":", 1)[1] if ":" in chat_response else ""

                def run_vision():
                    self.gui_queue.put(("status", "gemini_thinking"))
                    self.gui_queue.put(("message", ("OmniMind", "Sto guardando lo schermo. Analisi in corso...")))
                    self.tts_manager.speak("Analizzo lo schermo. Un attimo.")

                    self.gui_queue.put(("flash_screen", None))
                    response, img_path = self.gemini_client.analyze_screenshot(prompt)
                    self.gui_queue.put(("show_image", img_path))

                    self.gui_queue.put(("message", ("OmniMind", response)))
                    save_chat_message("OmniMind", response)
                    self.gui_queue.put(("status", "speaking"))
                    self.tts_manager.speak(response)

                    self._ripristina_ascolto()

                self._avvia_azione(run_vision, "l'analisi dello schermo")
                return True

            # Automazione Fisica RPA
            elif chat_response.startswith("rpa_trigger:"):
                prompt = chat_response.split(":", 1)[1] if ":" in chat_response else ""

                def run_rpa():
                    self.gui_queue.put(("status", "gemini_thinking"))
                    self.gui_queue.put(("message", ("OmniMind", "Sto elaborando la sequenza di automazione RPA...")))
                    self.tts_manager.speak("Elaboro l'automazione richiesta. Un attimo.")

                    try:
                        json_str = self.gemini_client.build_rpa_sequence(prompt)
                        rpa_sequence = json.loads(json_str)

                        if not isinstance(rpa_sequence, list):
                            raise ValueError("La sequenza generata non e' una lista di azioni.")
                        if len(rpa_sequence) > MAX_STEP_RPA:
                            raise ValueError(
                                f"Sequenza troppo lunga ({len(rpa_sequence)} passi, massimo {MAX_STEP_RPA}).")

                        # Velocita' di digitazione: impostazione gia' presente in GUI
                        # ma finora mai applicata.
                        intervallo = INTERVALLI_DIGITAZIONE.get(
                            self.config_data.get("rpa_typing_delay", "Normale"), 0.01)

                        for step in rpa_sequence:
                            action = step.get("action")
                            target = step.get("target")

                            if action == "open_app":
                                if str(target).startswith("http"):
                                    webbrowser.open(target)
                                else:
                                    # Nessun os.system: il target proviene dal modello e
                                    # una f-string dentro cmd.exe permette di concatenare
                                    # comandi con un semplice doppio apice.
                                    eseguibile = shutil.which(str(target))
                                    if eseguibile:
                                        subprocess.Popen([eseguibile], shell=False,
                                                         cwd=os.environ.get("SystemRoot", "C:\\Windows"))
                                    else:
                                        os.startfile(target)
                            elif action == "type_text":
                                pyautogui.write(str(target), interval=intervallo)
                            elif action == "press_key":
                                pyautogui.press(str(target))
                            elif action == "hotkey":
                                keys = [k.strip().lower() for k in str(target).split(',')]
                                if tuple(sorted(keys)) in HOTKEY_VIETATE:
                                    raise ValueError(f"Combinazione di tasti non consentita: {'+'.join(keys)}")
                                pyautogui.hotkey(*keys)
                            elif action == "sleep":
                                time.sleep(min(float(target), 10.0))

                        success_msg = "Automazione completata con successo."
                        self.gui_queue.put(("message", ("OmniMind", success_msg)))
                        save_chat_message("OmniMind", success_msg)
                        self.gui_queue.put(("status", "speaking"))
                        self.tts_manager.speak("Automazione completata.")

                    except Exception as e:
                        err_msg = f"Errore nell'esecuzione RPA: {e}"
                        self.gui_queue.put(("message", ("OmniMind", err_msg)))
                        save_chat_message("OmniMind", err_msg)
                        self.gui_queue.put(("status", "speaking"))
                        self.tts_manager.speak("Si è verificato un errore durante l'automazione.")

                    self._ripristina_ascolto()

                self._avvia_azione(run_rpa, "l'automazione")
                return True

            elif chat_response.startswith("system_diagnostics_trigger:"):
                def run_sys_diag():
                    self.gui_queue.put(("status", "gemini_thinking"))
                    self.gui_queue.put(("message", ("OmniMind", "Interrogo i sensori della Scheda Video e della CPU...")))
                    from src.commands import get_system_snapshot
                    snapshot = get_system_snapshot()
                    response = self.gemini_client.analyze_system(snapshot, text)
                    self.gui_queue.put(("message", ("OmniMind", response)))
                    save_chat_message("OmniMind", response)
                    self.gui_queue.put(("status", "speaking"))
                    self.tts_manager.speak(response)
                    self._ripristina_ascolto()
                self._avvia_azione(run_sys_diag, "la diagnostica di sistema")
                return True

            elif chat_response.startswith("process_kill_trigger:"):
                target_app = chat_response.split(":", 1)[1]
                def run_kill():
                    import psutil
                    self.gui_queue.put(("status", "processing"))
                    ago = target_app.lower().strip()

                    if len(ago) < 3:
                        msg = "Nome troppo generico: servono almeno 3 caratteri per chiudere un programma."
                        self.gui_queue.put(("message", ("OmniMind", msg)))
                        self.tts_manager.speak(msg)
                        return

                    # Prima si raccolgono i candidati, poi si verifica l'intera lista.
                    # Killando durante l'iterazione, incontrare un processo protetto
                    # interrompeva il ciclo lasciando gia' chiusi quelli precedenti.
                    candidati = []
                    for proc in psutil.process_iter(['name', 'pid']):
                        try:
                            name = (proc.info['name'] or "")
                            if not name or ago not in name.lower():
                                continue
                            if proc.info['pid'] in (os.getpid(), os.getppid()):
                                continue
                            candidati.append((proc, name))
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue

                    protetti = sorted({n for _p, n in candidati if n.lower() in PROCESSI_PROTETTI})
                    if protetti:
                        msg = (f"Sicurezza attiva: '{target_app}' corrisponde a processi di sistema "
                               f"({', '.join(protetti)}). Non ho chiuso nulla.")
                        self.gui_queue.put(("message", ("OmniMind", msg)))
                        self.tts_manager.speak("Ho annullato: la richiesta tocca processi di sistema.")
                        return

                    if not candidati:
                        msg = f"Nessun programma trovato con il nome {target_app}."
                        self.gui_queue.put(("message", ("OmniMind", msg)))
                        self.tts_manager.speak(msg)
                        return

                    chiusi = []
                    for proc, name in candidati:
                        try:
                            proc.terminate()   # chiusura ordinata, non kill immediato
                            chiusi.append(name)
                        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                            logger.warning(f"Impossibile terminare {name}: {e}")

                    _vivi, ancora_attivi = psutil.wait_procs([p for p, _n in candidati], timeout=3)
                    for proc in ancora_attivi:
                        try:
                            proc.kill()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass

                    msg = (f"Terminati {len(chiusi)} processi: {', '.join(sorted(set(chiusi)))}."
                           if chiusi else f"Nessun processo di {target_app} e' stato chiuso.")
                    self.gui_queue.put(("message", ("OmniMind", msg)))
                    self.tts_manager.speak(msg)
                    self._ripristina_ascolto()
                self._avvia_azione(run_kill, "la chiusura dei processi")
                return True

            # 3. Riassunto Documenti
            elif chat_response.startswith("doc_summary_trigger:"):
                path = chat_response.split(":", 1)[1] if ":" in chat_response else ""

                def run_doc_summary():
                    self.gui_queue.put(("status", "gemini_thinking"))
                    self.gui_queue.put(("message", ("OmniMind", f"Analisi del documento `{path}` in corso...")))
                    self.tts_manager.speak("Leggo il documento e preparo il riassunto.")

                    response = self.gemini_client.summarize_document(path)

                    self.gui_queue.put(("message", ("OmniMind", response)))
                    save_chat_message("OmniMind", response)
                    self.gui_queue.put(("status", "speaking"))
                    self.tts_manager.speak("Ho completato il riassunto del documento. Puoi leggerlo nella chat.")

                    self._ripristina_ascolto()

                self._avvia_azione(run_doc_summary, "il riassunto del documento")
                return True

            # 4. Consulente di Build (Gaming Expert)
            elif chat_response.startswith("gaming_expert_trigger:"):
                query = chat_response.split(":", 1)[1] if ":" in chat_response else ""

                def run_gaming():
                    self.gui_queue.put(("status", "gemini_thinking"))
                    self.gui_queue.put(("message", ("OmniMind", "Consulenza eSports coach in corso...")))

                    response = self.gemini_client.gaming_expert_advice(query)

                    self.gui_queue.put(("message", ("OmniMind", response)))
                    save_chat_message("OmniMind", response)
                    self.gui_queue.put(("status", "speaking"))
                    self.tts_manager.speak(response)

                    self._ripristina_ascolto()

                self._avvia_azione(run_gaming, "la consulenza di gioco")
                return True

            # 5. Traduttore Istantaneo
            elif chat_response.startswith("translate_trigger:"):
                parts = chat_response.split(":", 2)
                lang = parts[1]
                phrase = parts[2]

                def run_translation():
                    self.gui_queue.put(("status", "gemini_thinking"))

                    response = self.gemini_client.translate_phrase(phrase, lang)

                    self.gui_queue.put(("message", ("OmniMind", f"Traduzione in {lang.title()}:\n{response}")))
                    save_chat_message("OmniMind", f"Traduzione in {lang.title()}:\n{response}")
                    self.gui_queue.put(("status", "speaking"))
                    self.tts_manager.speak(response)

                    self._ripristina_ascolto()

                self._avvia_azione(run_translation, "la traduzione")
                return True

            # 6. Monitor Clipboard con IA (Fase 5 - Novità)
            elif chat_response.startswith("clipboard_analyze_trigger:"):
                def run_clipboard_analysis():
                    self.gui_queue.put(("status", "gemini_thinking"))
                    self.gui_queue.put(("message", ("OmniMind", "Sto leggendo e analizzando il testo negli appunti di Windows...")))
                    self.tts_manager.speak("Analizzo gli appunti. Un attimo.")

                    try:
                        import pyperclip
                        copied_text = pyperclip.paste()
                        if not copied_text or not copied_text.strip():
                            self.gui_queue.put(("message", ("OmniMind", "Gli appunti sono vuoti o non contengono testo valido.")))
                            self.tts_manager.speak("Gli appunti sono vuoti.")
                        else:
                            prompt = costruisci_prompt_dati(
                                "Analizza il testo che l'utente ha copiato negli appunti di Windows. "
                                "Traducilo se è in un'altra lingua, riassumilo o spiegalo in modo chiaro e conciso.",
                                copied_text)
                            response_text, audio_path = self.gemini_client.send_message(prompt)
                            self.gui_queue.put(("message", ("OmniMind", response_text)))
                            save_chat_message("OmniMind", response_text)
                            self.gui_queue.put(("status", "speaking"))
                            self.tts_manager.speak(response_text, audio_path=audio_path)
                    except Exception as e:
                        logger.error(f"Errore durante l'analisi del clipboard: {e}")
                        self.gui_queue.put(("message", ("OmniMind", f"Errore nell'analisi degli appunti: {e}")))

                    self._ripristina_ascolto()

                self._avvia_azione(run_clipboard_analysis, "l'analisi degli appunti")
                return True

            # Altri comandi sincroni
            else:
                self.gui_queue.put(("message", ("OmniMind", chat_response)))
                save_chat_message("OmniMind", chat_response)
                self.gui_queue.put(("status", "speaking"))
                self.tts_manager.speak(voice_response)

                # Se il comando ha modificato i profili, ricarica a runtime
                if "Profilo" in chat_response or "profili" in chat_response:
                    self.reload_settings(load_config())
                    self.gui_queue.put(("reload_config", None))
                return False

        elif chat_response == "ask_search_confirm":
            self.attesa_conferma_ricerca = True
            self.query_sospesa = voice_response

            richiesta_conferma = "Non sono riuscito a trovare questa applicazione sul PC. Vuoi che la cerchi su Google?"
            self.gui_queue.put(("message", ("OmniMind", richiesta_conferma)))
            save_chat_message("OmniMind", richiesta_conferma)
            self.gui_queue.put(("status", "speaking"))
            self.tts_manager.speak(richiesta_conferma)
            return False

        else:
            self.gui_queue.put(("status", "gemini_thinking"))
            response_text, audio_path = self.gemini_client.send_message(text)
            self.gui_queue.put(("message", ("OmniMind", response_text)))
            save_chat_message("OmniMind", response_text)
            self.gui_queue.put(("status", "speaking"))
            self.tts_manager.speak(response_text, audio_path=audio_path)
            return False

    def _safe_exit(self):
        """Spegne la GUI in modo sicuro e termina il processo Python."""
        try:
            self.gui.close()
            from PyQt6.QtWidgets import QApplication
            QApplication.quit()
        except Exception as e:
            logger.error(f"Errore durante la chiusura sicura della GUI: {e}")
        sys.exit(0)

    def exit_app(self, icon=None, item=None):
        """Ferma tutti i thread in esecuzione ed esce in sicurezza dal programma."""
        logger.info("Avvio procedura di chiusura applicazione...")
        self.running = False

        if self.wakeword_detector:
            self.wakeword_detector.stop()

        self.time_manager.stop()
        self.tts_manager.stop()
        self.tray.stop()

        # Ferma i timer Qt e il thread di polling della Dashboard.
        try:
            self.gui.shutdown()
        except Exception as e:
            logger.warning(f"Errore nell'arresto dei timer della GUI: {e}")

        if hasattr(self, 'context_monitor'):
            self.context_monitor.running = False
            # Chiudi l'event loop del ContextMonitor per sbloccare il thread
            if hasattr(self.context_monitor, 'loop') and self.context_monitor.loop:
                self.context_monitor.loop.call_soon_threadsafe(self.context_monitor.loop.stop)

        # Schedula la chiusura sul thread principale della GUI
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self._safe_exit)

from PyQt6.QtWidgets import QApplication

def main():
    # Inizializzazione applicazione Qt
    app_qt = QApplication(sys.argv)

    # Inizializzazione dell'applicazione OmniMind
    app = OmniMindAssistant()

    # Avvia l'event loop di Qt
    sys.exit(app_qt.exec())

if __name__ == "__main__":
    main()
