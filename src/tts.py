import os
import sys
import re
import uuid
import asyncio
import logging
import threading

sys.modules['aiodns'] = None  # Forza aiohttp a usare il resolver Threaded nativo invece di aiodns
import pygame
import edge_tts
from src.config import load_config, TEMP_DIR

logger = logging.getLogger("OmniMindTTS")

class TTSManager:
    """
    Gestisce la sintesi vocale (TTS) e la riproduzione audio asincrona.
    Supporta edge-tts (gratuito) per i comandi locali e la riproduzione dell'audio nativo di Gemini.
    Consente l'interruzione immediata dell'audio ed il controllo dinamico del volume.
    """
    def __init__(self):
        self.current_temp_file = None
        self._stop_event = threading.Event()
        
        # Carica le impostazioni iniziali
        config = load_config()
        self.voice = config.get("tts_voice", "it-IT-GiuseppeNeural")
        self.volume = config.get("volume", 1.0)
        
        # Impostazioni per controlli audio avanzati
        self.tts_rate = config.get("tts_rate", 0)
        self.tts_pitch = config.get("tts_pitch", 0)
        
        # Inizializza il mixer audio di pygame
        try:
            pygame.mixer.init()
            pygame.mixer.music.set_volume(self.volume)
            logger.info("pygame.mixer inizializzato con successo.")
        except Exception as e:
            logger.error(f"Errore di inizializzazione pygame.mixer: {e}")

    def set_volume(self, volume: float):
        """Aggiorna il volume di riproduzione a runtime."""
        self.volume = max(0.0, min(1.0, float(volume)))
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.set_volume(self.volume)
                logger.debug(f"Volume impostato a: {self.volume}")
        except Exception as e:
            logger.error(f"Errore nell'impostazione del volume: {e}")

    def set_voice(self, voice_name: str):
        """Aggiorna la voce TTS a runtime."""
        self.voice = voice_name
        logger.info(f"Voce TTS aggiornata a: {self.voice}")

    def update_settings(self, config: dict):
        """Aggiorna le impostazioni a runtime dopo un salvataggio delle impostazioni."""
        self.set_voice(config.get("tts_voice", "it-IT-GiuseppeNeural"))
        self.set_volume(config.get("volume", 1.0))
        
        # Aggiorna a runtime le nuove opzioni audio
        self.tts_rate = config.get("tts_rate", 0)
        self.tts_pitch = config.get("tts_pitch", 0)

    def stop(self):
        """Interrompe immediatamente la riproduzione audio in corso."""
        self._stop_event.set()
        try:
            if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                logger.info("Riproduzione audio interrotta dall'utente.")
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
        except Exception as e:
            logger.error(f"Errore durante l'interruzione della musica: {e}")
            
        self._clean_temp_file()

    def _clean_temp_file(self):
        """Rimuove il file audio temporaneo generato in precedenza."""
        if self.current_temp_file and os.path.exists(self.current_temp_file):
            try:
                os.remove(self.current_temp_file)
                logger.debug(f"File temporaneo audio rimosso: {self.current_temp_file}")
            except Exception as e:
                logger.warning(f"Impossibile rimuovere il file temporaneo {self.current_temp_file}: {e}")
            self.current_temp_file = None

    def speak(self, text: str, audio_path: str = None):
        """
        Sintetizza il testo e lo riproduce, o riproduce direttamente il file audio se fornito.
        Questo metodo blocca il thread in cui viene eseguito, ma può essere
        interrotto da un altro thread chiamando il metodo stop().
        """
        # Ferma eventuale riproduzione precedente
        self.stop()
        self._stop_event.clear()
        
        # Silenzia le risposte vocali se Focus Mode è attiva con opzione Mute TTS
        config = load_config()
        if config.get("focus_mode_active", False) and config.get("focus_mute_tts", True):
            logger.info("Sintesi vocale annullata: Modalità Focus attiva con opzione Muta TTS.")
            return

        if audio_path and os.path.exists(audio_path):
            logger.info(f"Riproduzione audio nativo diretto fornito: {audio_path}")
            self.current_temp_file = audio_path
        else:
            if not text or not text.strip():
                return

            # Pulisce il testo dal markdown prima di passarlo al TTS
            text_to_speak = text
            text_to_speak = re.sub(r'\*+', '', text_to_speak)  # Rimuove tutti gli asterischi (* e **)
            text_to_speak = re.sub(r'#+', '', text_to_speak)   # Rimuove i cancelletti dei titoli
            text_to_speak = re.sub(r'`+', '', text_to_speak)   # Rimuove i backtick del codice

            # Genera un file temporaneo univoco in formato MP3
            temp_filename = f"omnimind_voice_{uuid.uuid4().hex}.mp3"
            self.current_temp_file = os.path.join(TEMP_DIR, temp_filename)

            try:
                logger.info(f"Sintesi standard con edge-tts (voce: {self.voice}, rate: {self.tts_rate}%, pitch: {self.tts_pitch}Hz)...")
                # Imposta la policy per aiohttp su Windows (Evita l'errore del ProactorEventLoop)
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
                # Esegue la coroutine edge-tts in modo sincrono nel thread corrente
                asyncio.run(self._generate_edgetts(text_to_speak, self.current_temp_file))
            except Exception as e:
                logger.error(f"Errore durante la generazione dell'audio: {e}")
                self._clean_temp_file()
                return

        # Riproduzione
        try:
            if self.current_temp_file and os.path.exists(self.current_temp_file) and pygame.mixer.get_init():
                pygame.mixer.music.load(self.current_temp_file)
                pygame.mixer.music.set_volume(self.volume)
                pygame.mixer.music.play()
                
                # Attende che la riproduzione finisca o venga interrotta esternamente
                clock = pygame.time.Clock()
                while pygame.mixer.music.get_busy() and not self._stop_event.is_set():
                    clock.tick(10)
                
                pygame.mixer.music.unload()
        except Exception as e:
            logger.error(f"Errore durante la riproduzione dell'audio: {e}")
        finally:
            self._clean_temp_file()

    async def _generate_edgetts(self, text: str, output_path: str):
        """Genera l'audio usando edge-tts con controlli di rate e pitch."""
        rate_str = f"{self.tts_rate:+d}%"
        pitch_str = f"{self.tts_pitch:+d}Hz"
        communicate = edge_tts.Communicate(text, self.voice, rate=rate_str, pitch=pitch_str)
        await communicate.save(output_path)
