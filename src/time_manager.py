import time
import datetime
import threading
import logging
import io
import wave
import math
import struct
from src.config import load_config
from src.database import (
    salva_timer, rimuovi_timer, leggi_timers,
    salva_sveglia, rimuovi_sveglia, leggi_sveglie,
)

logger = logging.getLogger("OmniMindTimeManager")

def generate_alert_wav() -> bytes:
    """
    Genera dinamicamente in memoria un file WAV di 5.0 secondi contenente un tono d'allarme
    pulsato (480Hz) con fade-in graduale nei primi 4 secondi per renderlo meno aggressivo.
    """
    sample_rate = 44100
    duration = 5.0
    frequency = 480.0  # Frequenza più bassa e calda (480Hz)

    buf = io.BytesIO()
    try:
        with wave.open(buf, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)

            num_samples = int(sample_rate * duration)
            for i in range(num_samples):
                t = float(i) / sample_rate
                # Crea un effetto pulsato spegnendo il suono ogni 300ms
                pulse = 1.0 if (int(t * 3.33) % 2 == 0) else 0.0
                # Fade-in lineare nei primi 4 secondi
                fade = min(1.0, t / 4.0)

                value = int(25000.0 * math.sin(2.0 * math.pi * frequency * t) * pulse * fade)
                wav.writeframesraw(struct.pack('<h', value))
        return buf.getvalue()
    except Exception as e:
        logger.error(f"Errore nella generazione del tono audio in memoria: {e}")
        return b""

class TimeManager:
    """
    Gestisce sveglie e timer sovrapposti in esecuzione parallela (multi-thread).
    Notifica la GUI e riproduce un allarme sonoro allo scadere degli eventi.
    """
    def __init__(self, gui_queue):
        self.gui_queue = gui_queue
        self.timers = []  # Lista di dict: {"id": str, "seconds_left": int, "label": str, "total": int}
        self.alarms = []  # Lista di dict: {"id": str, "time_str": str, "label": str, "triggered": bool}
        self.lock = threading.Lock()
        self.running = True
        self.sound = None

        # Inizializza pygame.mixer
        try:
            import pygame
            # Evita di re-inizializzare se già inizializzato
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            wav_bytes = generate_alert_wav()
            if wav_bytes:
                self.sound = pygame.mixer.Sound(io.BytesIO(wav_bytes))
                logger.info("Audio d'allarme pygame.mixer inizializzato con successo in memoria.")
        except Exception as e:
            logger.warning(f"pygame.mixer non disponibile o errore inizializzazione. Fallback su winsound: {e}")

        # Ripristina quanto era stato impostato prima della chiusura
        self._ripristina_da_db()

        # Avvia il thread di monitoraggio
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("Thread di monitoraggio TimeManager avviato correttamente.")

    def _ripristina_da_db(self):
        """Ricarica timer e sveglie salvati: prima si perdevano ad ogni chiusura."""
        adesso = datetime.datetime.now()
        try:
            for tid, label, deadline_iso, total in leggi_timers():
                scadenza = datetime.datetime.fromisoformat(deadline_iso)
                if scadenza <= adesso:
                    rimuovi_timer(tid)      # gia' scaduto mentre l'app era chiusa
                    continue
                self.timers.append({"id": tid, "label": label,
                                    "deadline": scadenza, "total": total})

            for aid, time_str, label, created_iso in leggi_sveglie():
                self.alarms.append({"id": aid, "time_str": time_str, "label": label,
                                    "triggered": False,
                                    "created_at": datetime.datetime.fromisoformat(created_iso)})

            if self.timers or self.alarms:
                logger.info(f"Ripristinati {len(self.timers)} timer e {len(self.alarms)} sveglie dal database.")
        except Exception as e:
            logger.error(f"Errore nel ripristino di timer e sveglie: {e}")

    def add_timer(self, seconds: int, label: str = "Timer"):
        """Aggiunge un nuovo timer simultaneo."""
        timer_id = f"timer_{int(time.time())}_{seconds}"
        # Scadenza assoluta invece di un contatore decrementato ogni secondo:
        # resiste al riavvio e non accumula deriva se il thread viene ritardato.
        scadenza = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
        with self.lock:
            self.timers.append({
                "id": timer_id,
                "deadline": scadenza,
                "label": label,
                "total": seconds
            })
        salva_timer(timer_id, label, scadenza.isoformat(), seconds)
        logger.info(f"Timer '{label}' impostato per {seconds} secondi.")

        # Invia messaggio di conferma immediato
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        parts = []
        if hours > 0: parts.append(f"{hours} ore")
        if minutes > 0: parts.append(f"{minutes} minuti")
        if secs > 0 or not parts: parts.append(f"{secs} secondi")
        duration_str = ", ".join(parts)

        self.gui_queue.put(("message", ("OmniMind", f"⏰ **Timer Impostato!**\n- Evento: `{label}`\n- Durata: {duration_str}")))

    def add_alarm(self, time_str: str, label: str = "Sveglia"):
        """Aggiunge una nuova sveglia ad un orario specifico (HH:MM)."""
        alarm_id = f"alarm_{int(time.time())}_{time_str.replace(':', '_')}"
        creata = datetime.datetime.now()
        with self.lock:
            self.alarms.append({
                "id": alarm_id,
                "time_str": time_str,
                "label": label,
                "triggered": False,
                # Istante di creazione: senza di esso una sveglia impostata per
                # un orario appena passato rientrava nella finestra di 5 minuti
                # e suonava immediatamente.
                "created_at": creata
            })
        salva_sveglia(alarm_id, time_str, label, creata.isoformat())
        logger.info(f"Sveglia '{label}' impostata per le {time_str}.")
        self.gui_queue.put(("message", ("OmniMind", f"⏰ **Sveglia Impostata!**\n- Evento: `{label}`\n- Orario: {time_str}")))

    def _play_alert_sound(self):
        """Riproduce l'allarme sonoro in un thread separato per evitare blocchi."""
        def play():
            try:
                if self.sound:
                    # Carica la configurazione aggiornata a runtime
                    config = load_config()
                    alarm_vol = float(config.get("alarm_volume", 0.50))
                    self.sound.set_volume(alarm_vol)

                    # Riproduce l'allarme 2 volte consecutive
                    self.sound.play(loops=1)
                    return
            except Exception as e:
                logger.warning(f"Impossibile riprodurre con pygame: {e}. Tento winsound.")

            try:
                import winsound
                # Utilizza l'allarme di sistema asincrono nativo di Windows
                winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
            except Exception as e:
                logger.error(f"Errore nella riproduzione con winsound: {e}")

        threading.Thread(target=play, daemon=True).start()

    def _monitor_loop(self):
        """Loop di monitoraggio eseguito ogni secondo in background."""
        while self.running:
            time.sleep(1)

            now_dt = datetime.datetime.now()
            current_time_str = now_dt.strftime("%H:%M")

            # Gestione dei Timer (confronto su scadenza assoluta)
            expired_timers = []
            with self.lock:
                for t in self.timers:
                    if now_dt >= t["deadline"]:
                        expired_timers.append(t)

                self.timers = [t for t in self.timers if now_dt < t["deadline"]]

            for t in expired_timers:
                rimuovi_timer(t["id"])

            # Notifica i timer scaduti
            for t in expired_timers:
                logger.info(f"Timer '{t['label']}' scaduto!")
                self.gui_queue.put(("message", ("OmniMind", f"🔔 **TIMER SCADUTO!**\nIl timer per `{t['label']}` ({t['total']} secondi) è terminato!")))
                self.gui_queue.put(("show_overlay", (f"Timer Scaduto!\n{t['label']}", 7)))
                self._play_alert_sound()

            # Gestione delle Sveglie
            triggered_alarms = []
            with self.lock:
                for a in self.alarms:
                    try:
                        h, m = map(int, a["time_str"].split(':'))
                        alarm_minutes = h * 60 + m
                    except Exception:
                        continue

                    now_minutes = now_dt.hour * 60 + now_dt.minute
                    diff = (now_minutes - alarm_minutes) % 1440

                    # La sveglia puo' scattare solo per un orario successivo al
                    # momento in cui e' stata creata.
                    creata = a.get("created_at")
                    if creata is not None:
                        creata_minuti = creata.hour * 60 + creata.minute
                        if (creata_minuti - alarm_minutes) % 1440 <= 5:
                            continue

                    if not a["triggered"] and diff <= 5:
                        a["triggered"] = True
                        triggered_alarms.append(a)

                # Rimuove le sveglie attivate
                self.alarms = [a for a in self.alarms if not a["triggered"]]

            for a in triggered_alarms:
                rimuovi_sveglia(a["id"])

            # Notifica le sveglie suonate
            for a in triggered_alarms:
                logger.info(f"Sveglia '{a['label']}' attivata!")
                self.gui_queue.put(("message", ("OmniMind", f"🔔 **SVEGLIA!**\nLa sveglia per `{a['label']}` impostata per le {a['time_str']} sta suonando!")))
                self.gui_queue.put(("show_overlay", (f"Sveglia!\n{a['label']}", 7)))
                self._play_alert_sound()

    def stop(self):
        """Ferma il thread di monitoraggio."""
        self.running = False
