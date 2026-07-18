import os
import zipfile
import urllib.request
import winsound
import shutil
import logging
from pathlib import Path
from src.config import MODEL_DIR

logger = logging.getLogger("OmniMindUtils")

VOSK_MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-it-0.22.zip"
VOSK_MODEL_NAME = "vosk-model-small-it-0.22"

def play_beep(freq=1000, duration=150):
    """Riproduce un breve feedback sonoro (bip) su Windows."""
    try:
        winsound.Beep(freq, duration)
    except Exception as e:
        logger.error(f"Errore durante la riproduzione del bip: {e}")

def ensure_vosk_model(status_callback=None):
    """
    Verifica se il modello Vosk italiano è presente.
    Se non lo è, lo scarica e lo decomprime nella cartella src/model.
    status_callback è una funzione opzionale che accetta una stringa con lo stato.
    """
    model_path = MODEL_DIR / VOSK_MODEL_NAME
    
    # Se la cartella del modello esiste già, restituisce il percorso
    if model_path.exists() and (model_path / "am").exists():
        logger.info(f"Modello Vosk trovato in: {model_path}")
        return str(model_path)
    
    logger.info("Modello Vosk italiano non trovato. Avvio download...")
    if status_callback:
        status_callback("Download modello di lingua (45MB)...")
        
    zip_path = MODEL_DIR / f"{VOSK_MODEL_NAME}.zip"
    
    # Rimuove cartelle corrotte se presenti
    if model_path.exists():
        shutil.rmtree(model_path)
        
    try:
        # Download con tracciamento del progresso
        def progress_hook(count, block_size, total_size):
            percent = int(count * block_size * 100 / total_size)
            percent = min(100, percent)
            msg = f"Download modello vocale... {percent}%"
            logger.info(msg)
            if status_callback and percent % 5 == 0:
                status_callback(msg)

        urllib.request.urlretrieve(VOSK_MODEL_URL, zip_path, reporthook=progress_hook)
        
        logger.info("Download completato. Estrazione in corso...")
        if status_callback:
            status_callback("Estrazione del modello...")
            
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(MODEL_DIR)
            
        logger.info("Estrazione completata con successo.")
        if status_callback:
            status_callback("Modello pronto.")
            
        # Rimuove il file zip temporaneo
        if zip_path.exists():
            os.remove(zip_path)
            
        return str(model_path)
        
    except Exception as e:
        logger.error(f"Errore durante il download o estrazione del modello Vosk: {e}")
        if zip_path.exists():
            try:
                os.remove(zip_path)
            except Exception:
                pass
        if status_callback:
            status_callback("Errore download modello.")
        raise e
