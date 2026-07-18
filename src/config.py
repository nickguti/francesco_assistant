import os
import json
import threading
from pathlib import Path
from dotenv import load_dotenv

# Definisce le directory di base
BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
MODEL_DIR = SRC_DIR / "model"
TEMP_DIR = BASE_DIR / "temp"
CONFIG_FILE = BASE_DIR / "config.json"

# Assicura l'esistenza delle cartelle necessarie
MODEL_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Carica le variabili dal file .env come fallback iniziale
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

# Valori di default iniziali (compreso il volume)
DEFAULT_CONFIG = {
    "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
    "wake_word": os.getenv("WAKE_WORD", "omnimind").lower().strip(),
    "tts_voice": os.getenv("TTS_VOICE", "it-IT-GiuseppeNeural"),
    "volume": 1.0,
    "gemini_model": "gemini-2.5-flash",
    "temperature": 0.7,
    "mic_sensitivity": 400,
    "theme": "Scuro",
    "accent_color": "Azzurro",
    "start_with_windows": False,
    "start_minimized": False,
    "elevenlabs_api_key": os.getenv("ELEVENLABS_API_KEY", ""),
    "elevenlabs_voice_id": os.getenv("ELEVENLABS_VOICE_ID", ""),
    "spotify_client_id": os.getenv("SPOTIFY_CLIENT_ID", ""),
    "spotify_client_secret": os.getenv("SPOTIFY_CLIENT_SECRET", ""),
    "spotify_redirect_uri": os.getenv("SPOTIFY_REDIRECT_URI", ""),
    "focus_mode_active": False,
    "focus_mute_tts": True,
    "focus_close_apps": True,
    "focus_block_notifications": False,
    "active_profile": "Nessuno",
    "gaming_volume": 0.30,
    "gaming_open_launchers": True,
    "gaming_optimize_ram": True,
    "alarm_volume": 0.50,
    "std_brightness": 80,
    "night_volume": 0.15,
    "night_brightness": 15,
    "tts_rate": 0,
    "tts_pitch": 0,
    "tts_engine": "Microsoft Edge (Gratis)",
    "openai_api_key": "",
    "openai_voice": "onyx",
    "rpa_typing_delay": "Normale",
    "rpa_auto_enter": True,
    "safe_mode_confirm": False,
    "log_level": "Info",
    "gaming_high_performance": True,
    "gaming_kill_browsers": False,
    "focus_pomodoro": False,
    "focus_lofi": False,
    "night_blue_light": True,
    "night_sleep_timer": "Mai",
    "trigger_time_night": "",
    "trigger_app_gaming": ""
}

_config_lock = threading.Lock()
_cached_config = None
_last_mtime = 0.0

def load_config() -> dict:
    """
    Carica la configurazione da config.json, creandolo se non esiste.
    Utilizza un sistema di caching basato sul timestamp di modifica del file (mtime)
    per garantire la sincronizzazione a runtime senza pesare sul disco ad ogni lettura,
    essendo thread-safe per un accesso concorrente.
    """
    global _cached_config, _last_mtime
    
    with _config_lock:
        if not CONFIG_FILE.exists():
            save_config_internal(DEFAULT_CONFIG)
            _cached_config = DEFAULT_CONFIG.copy()
            _last_mtime = os.path.getmtime(CONFIG_FILE)
            return _cached_config.copy()
            
        try:
            current_mtime = os.path.getmtime(CONFIG_FILE)
            if _cached_config is not None and current_mtime <= _last_mtime:
                return _cached_config.copy()
                
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                
            updated = False
            for key, val in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = val
                    updated = True
                    
            if updated:
                save_config_internal(config)
                current_mtime = os.path.getmtime(CONFIG_FILE)
                
            _cached_config = config
            _last_mtime = current_mtime
            return config.copy()
            
        except Exception as e:
            print(f"Errore nella lettura di config.json ({e}). Utilizzo i valori in cache o di default.")
            if _cached_config is not None:
                return _cached_config.copy()
            return DEFAULT_CONFIG.copy()

def save_config_internal(config_data: dict):
    """Versione interna senza lock per evitare deadlock ricorsivi."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Errore nel salvataggio del file config.json: {e}")

def save_config(config_data: dict):
    """Salva i dati di configurazione correnti all'interno del file config.json."""
    with _config_lock:
        save_config_internal(config_data)
        global _cached_config, _last_mtime
        _cached_config = config_data.copy()
        try:
            _last_mtime = os.path.getmtime(CONFIG_FILE)
        except OSError:
            pass

def get_setting(key: str, default=None):
    """
    Ritorna il valore aggiornato di una singola impostazione a runtime.
    Garantisce la sincronizzazione senza necessita' di restart.
    """
    config = load_config()
    return config.get(key, default)

# Configurazione iniziale a caricamento immediato (retrocompatibilita')
_current_config = load_config()

GEMINI_API_KEY = _current_config["gemini_api_key"]
WAKE_WORD = _current_config["wake_word"]
TTS_VOICE = _current_config["tts_voice"]
VOLUME = _current_config["volume"]
ELEVENLABS_API_KEY = _current_config["elevenlabs_api_key"]
ELEVENLABS_VOICE_ID = _current_config["elevenlabs_voice_id"]
SPOTIFY_CLIENT_ID = _current_config["spotify_client_id"]
SPOTIFY_CLIENT_SECRET = _current_config["spotify_client_secret"]
SPOTIFY_REDIRECT_URI = _current_config["spotify_redirect_uri"]
FOCUS_MODE_ACTIVE = _current_config.get("focus_mode_active", False)
FOCUS_MUTE_TTS = _current_config.get("focus_mute_tts", True)
FOCUS_CLOSE_APPS = _current_config.get("focus_close_apps", True)
FOCUS_BLOCK_NOTIFICATIONS = _current_config.get("focus_block_notifications", False)
ACTIVE_PROFILE = _current_config.get("active_profile", "Nessuno")
GAMING_VOLUME = _current_config.get("gaming_volume", 0.30)
GAMING_OPEN_LAUNCHERS = _current_config.get("gaming_open_launchers", True)
GAMING_OPTIMIZE_RAM = _current_config.get("gaming_optimize_ram", True)
ALARM_VOLUME = _current_config.get("alarm_volume", 0.50)
STD_BRIGHTNESS = _current_config.get("std_brightness", 80)
NIGHT_VOLUME = _current_config.get("night_volume", 0.15)
NIGHT_BRIGHTNESS = _current_config.get("night_brightness", 15)
START_MINIMIZED = _current_config.get("start_minimized", False)
