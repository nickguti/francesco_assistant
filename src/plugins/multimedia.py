import re
import pyautogui
import webbrowser
import logging
import time
from src.plugins.base_plugin import OmniMindPlugin
from src.commands import play_track_real_spotify

logger = logging.getLogger("PluginMultimedia")

class MultimediaPlugin(OmniMindPlugin):
    """
    Gestisce i controlli multimediali rapidi e la riproduzione Spotify.
    """
    name = "Multimedia & Spotify"
    description = "Permette di controllare la musica su Spotify e gestire le shortcut multimediali play, pausa e scorrimento tracce."
    priority = 20
    examples = [
        ("metti in pausa", "Play/pausa del media in riproduzione"),
        ("prossima canzone", "Traccia successiva"),
        ("riproduci Bohemian Rhapsody su spotify", "Riproduzione via API Spotify"),
    ]

    def can_handle(self, text_clean: str, text: str) -> bool:
        triggers = [
            "metti in pausa", "stoppa la musica", "ferma la musica", "riprendi la musica", "metti play",
            "prossima canzone", "canzone successiva", "metti la prossima", "skippa canzone", "salta traccia",
            "canzone precedente", "rimetti da capo", "traccia precedente",
            "abbassa il volume di spotify", "abbassa spotify", "spotify più basso"
        ]
        if any(k in text_clean for k in triggers):
            return True
            
        if re.search(r'(?:riproduci|metti|cerca|ascolta)\s+(.+?)\s+su\s+spotify', text_clean):
            return True
            
        if re.search(r'(?:riproduci|metti|cerca|ascolta)\s+su\s+spotify\s+(.+)', text_clean):
            return True
            
        # Controlla anche il trigger di ricerca genetica "apri spotify" che è in apps_launcher ma se è per spotify lo gestiamo qui?
        # No, "apri spotify" lo lasciamo ad apps_launcher, qui gestiamo play/pause
        return False

    def execute(self, text_clean: str, text: str) -> tuple[bool, str, str]:
        # Shortcut rapidi
        if any(k in text_clean for k in ["metti in pausa", "stoppa la musica", "ferma la musica", "riprendi la musica", "metti play"]):
            pyautogui.press('playpause')
            return True, "Fatto. ⏸️", "Fatto."
            
        if any(k in text_clean for k in ["prossima canzone", "canzone successiva", "metti la prossima", "skippa canzone", "salta traccia"]):
            pyautogui.press('nexttrack')
            return True, "Skippata. ⏭️", "Canzone saltata."
            
        if any(k in text_clean for k in ["canzone precedente", "rimetti da capo", "traccia precedente"]):
            pyautogui.press('prevtrack')
            return True, "Indietro. ⏮️", "Fatto."
            
        if any(k in text_clean for k in ["abbassa il volume di spotify", "abbassa spotify", "spotify più basso"]):
            for _ in range(5): pyautogui.press('volumedown') # Abbassa di 5 step il volume master per coprire spotify
            return True, "Volume abbassato. 🔉", "Volume ridotto."

        # Gestione avanzata Spotify API
        spotify_match1 = re.search(r'(?:riproduci|metti|cerca|ascolta)\s+(.+?)\s+su\s+spotify', text_clean)
        spotify_match2 = re.search(r'(?:riproduci|metti|cerca|ascolta)\s+su\s+spotify\s+(.+)', text_clean)
        
        spotify_query = None
        if spotify_match1:
            spotify_query = spotify_match1.group(1).strip()
        elif spotify_match2:
            spotify_query = spotify_match2.group(1).strip()
            
        if spotify_query:
            logger.info(f"Ricevuta richiesta Spotify per: {spotify_query}")
            is_api_play, chat_resp, voice_resp = play_track_real_spotify(spotify_query)
            if is_api_play:
                return True, chat_resp, voice_resp
                
            # Fallback a webbrowser URI
            logger.info("Tentativo di fallback su URI locale di Spotify...")
            webbrowser.open(f"spotify:search:{spotify_query}")
            # L'automazione GUI sottostante era presente in commands.py
            time.sleep(2)
            pyautogui.press('enter')
            time.sleep(1)
            pyautogui.press('tab')
            pyautogui.press('enter')
            return True, f"Ricerca ed avvio riproduzione (Fallback) per: '{spotify_query}' su Spotify.", f"Faccio partire {spotify_query} su Spotify."

        return False, "", ""
