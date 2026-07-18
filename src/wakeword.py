import json
import queue
import time
import logging
import sounddevice as sd
import numpy as np
import speech_recognition as sr
from vosk import Model, KaldiRecognizer
logger = logging.getLogger("OmniMindWakeWord")

class WakeWordDetector:
    """
    Gestisce un unico stream audio persistente (sounddevice) sempre aperto.
    Implementa una macchina a stati per passare dall'ascolto offline della wake-word
    all'accumulo in memoria del comando parlato, rilevando la fine del silenzio tramite NumPy.
    """
    def __init__(self, model_path, on_wake_word_detected_callback, on_command_recorded_callback, wake_word):
        self.model_path = model_path
        self.on_wake_word_detected = on_wake_word_detected_callback
        self.on_command_recorded = on_command_recorded_callback
        self.wake_word = wake_word.lower().strip()
        
        logger.info("Caricamento del modello Vosk...")
        self.model = Model(model_path)
        self.recognizer = KaldiRecognizer(self.model, 16000)
        self.audio_queue = queue.Queue()
        
        # Stati della macchina: "listening_wakeword", "recording_command", "processing", "muted"
        self.state = "listening_wakeword"
        self.running = False
        self.paused = False  # Mute vocale comandato dall'utente
        self.stream = None
        
        # Buffer in memoria per accumulare i byte audio del comando
        self.command_buffer = []
        
        # Parametri di taratura del silenzio (Ammorbiditi per comandi lunghi)
        self.silence_threshold = 200.0      # Valore RMS ridotto per essere più sensibile alla voce bassa
        self.silence_timeout = 2.5          # Secondi di silenzio continuato per fermare la registrazione
        self.max_record_duration = 20.0     # Timeout di sicurezza esteso a 20s per automazioni complesse
        
        self.recording_start_time = 0.0
        self.silence_start_time = None

    def update_wake_word(self, new_wake_word):
        """Aggiorna la wake-word a runtime senza riavviare il thread acustico."""
        self.wake_word = new_wake_word.lower().strip()
        logger.info(f"Wake-word aggiornata dinamicamente a: '{self.wake_word}'")

    def _audio_callback(self, indata, frames, time_info, status):
        """Callback di sounddevice: accoda i byte audio senza bloccare il thread audio."""
        if status:
            logger.warning(f"Stato dell'input audio: {status}")
        self.audio_queue.put(bytes(indata))

    def run(self):
        """Loop di lettura ed instradamento dei byte audio in background. Eseguito in un thread."""
        self.running = True
        self.audio_queue.queue.clear()
        self.recognizer.Reset()
        
        try:
            # Apriamo l'UNICO stream audio permanente a 16kHz Mono Int16
            self.stream = sd.RawInputStream(
                samplerate=16000,
                blocksize=2000,     # Circa 125ms di finestra temporale
                dtype='int16',
                channels=1,
                callback=self._audio_callback
            )
            self.stream.start()
            logger.info("Stream audio persistente avviato. In ascolto della wake-word...")
            
            while self.running:
                try:
                    data = self.audio_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                
                # Gestione Mute Vocale
                if self.paused:
                    self.state = "muted"
                    continue
                elif self.state == "muted":
                    self.state = "listening_wakeword"

                # 1. STATO: ASCOLTO DELLA WAKE-WORD (Offline con Vosk)
                if self.state == "listening_wakeword":
                    if self.recognizer.AcceptWaveform(data):
                        result = json.loads(self.recognizer.Result())
                        text = result.get("text", "").lower()
                        if self.wake_word in text:
                            self._trigger_wake_word()
                    else:
                        # Rilevamento parziale per azzerare la latenza
                        partial = json.loads(self.recognizer.PartialResult())
                        partial_text = partial.get("partial", "").lower()
                        if self.wake_word in partial_text:
                            self._trigger_wake_word()

                # 2. STATO: REGISTRAZIONE COMANDO IN CORSO
                elif self.state == "recording_command":
                    # Accoda i byte in memoria
                    self.command_buffer.append(data)
                    
                    # Calcola l'ampiezza RMS del blocco per verificare se l'utente parla o tace
                    samples = np.frombuffer(data, dtype=np.int16)
                    rms = 0.0
                    if len(samples) > 0:
                        rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
                    
                    current_time = time.time()
                    
                    if rms > self.silence_threshold:
                        # L'utente sta parlando: resetta il timer del silenzio
                        self.silence_start_time = None
                    else:
                        # È silenzio: avvia o incrementa il timer
                        if self.silence_start_time is None:
                            self.silence_start_time = current_time
                    
                    # Calcolo durate
                    silence_duration = current_time - self.silence_start_time if self.silence_start_time else 0.0
                    total_duration = current_time - self.recording_start_time
                    
                    # Verifica se interrompere la cattura (silenzio terminato o tempo scaduto)
                    if (self.silence_start_time and silence_duration >= self.silence_timeout) or (total_duration >= self.max_record_duration):
                        logger.info(f"Fine registrazione. Durata: {total_duration:.2f}s, Silenzio rilevato: {silence_duration:.2f}s")
                        self._trigger_command_recorded()
                        
        except Exception as e:
            logger.error(f"Errore fatale nel loop di stream unificato: {e}")
            self.running = False
        finally:
            self.stop()

    def _trigger_wake_word(self):
        """Esegue lo switch dello stato a registrazione e notifica il main thread."""
        logger.info(f"Wake-word '{self.wake_word}' intercettata nello stream condiviso.")
        self.state = "recording_command"
        self.recognizer.Reset()
        self.command_buffer.clear()
        self.recording_start_time = time.time()
        self.silence_start_time = None
        
        # Chiama la callback per notificare main.py (che emetterà il bip e imposterà la GUI)
        self.on_wake_word_detected()

    def _trigger_command_recorded(self):
        """Converte il buffer in AudioData e lancia la callback di elaborazione."""
        self.state = "processing"
        raw_audio = b"".join(self.command_buffer)
        
        # Converte i byte audio grezzi in AudioData di SpeechRecognition (sample_width=2 per int16)
        audio_data = sr.AudioData(raw_audio, sample_rate=16000, sample_width=2)
        
        # Lancia la callback per avviare la trascrizione asincrona
        self.on_command_recorded(audio_data)

    def resume_listening(self):
        """Ripristina lo stato di ascolto offline. Chiamato alla fine dell'elaborazione/parlato."""
        self.command_buffer.clear()
        # Svuota la coda audio per evitare di processare chunk obsoleti
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
        self.recognizer.Reset()
        self.state = "listening_wakeword"
        logger.info("Ascolto wake-word ripristinato sullo stream unificato.")

    def stop(self):
        """Arresta lo stream e libera le risorse audio."""
        self.running = False
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception as e:
                logger.error(f"Errore nella chiusura dello stream sounddevice: {e}")
            self.stream = None
        logger.info("Stream audio persistente disattivato.")
