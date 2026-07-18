import logging
import speech_recognition as sr

logger = logging.getLogger("OmniMindSTT")

def transcribe_audio(audio_data: sr.AudioData) -> str:
    """
    Trascrive l'oggetto AudioData pre-registrato in memoria
    usando l'API Google Speech (in lingua italiana, gratuita e immediata).
    Non apre il microfono, prevenendo qualsiasi stallo del driver audio.
    """
    recognizer = sr.Recognizer()
    
    try:
        logger.info("Invio del buffer audio in memoria all'API di trascrizione...")
        command_text = recognizer.recognize_google(audio_data, language="it-IT")
        logger.info(f"Comando trascritto con successo: '{command_text}'")
        return command_text.strip()
        
    except sr.UnknownValueError:
        logger.warning("Trascrizione fallita: l'audio non è stato compreso.")
        return ""
    except sr.RequestError as e:
        logger.error(f"Errore di rete con l'API SpeechRecognition: {e}")
        return ""
    except Exception as e:
        logger.error(f"Errore imprevisto durante la trascrizione dell'audio: {e}")
        return ""
