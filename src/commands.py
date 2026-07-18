import os
import re
import time
import datetime
import webbrowser
import logging
import threading
import subprocess
import secrets
import string
import ctypes
import socket
import zipfile
import shutil
import gc
import json
from pathlib import Path
import urllib.parse
import pyperclip
import psutil
import requests
from pycaw.pycaw import AudioUtilities
from src.config import BASE_DIR, load_config, save_config

logger = logging.getLogger("OmniMindCommands")

# file JSON locale per la to-do list
TODO_FILE = BASE_DIR / "todo_list.json"

def get_system_snapshot() -> dict:
    data = {}
    import psutil, subprocess
    
    data["cpu_percent"] = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    data["ram_percent"] = ram.percent
    data["ram_used_gb"] = round(ram.used / (1024**3), 2)
    
    # Lettura silente NVIDIA-SMI
    try:
        smi = subprocess.check_output(
            ['nvidia-smi', '--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total', '--format=csv,noheader,nounits'],
            creationflags=0x08000000 # CREATE_NO_WINDOW per evitare popup console
        ).decode('utf-8').strip()
        if smi:
            util, temp, mem_used, mem_tot = [int(x.strip()) for x in smi.split(',')]
            data["gpu_percent"] = util
            data["gpu_temp_c"] = temp
            data["gpu_vram_used_mb"] = mem_used
    except Exception: pass
    
    procs = []
    for p in psutil.process_iter(['name', 'memory_percent']):
        try: procs.append(p.info)
        except Exception: pass
    procs.sort(key=lambda x: x.get('memory_percent', 0) or 0, reverse=True)
    data["top_ram_processes"] = procs[:5]
    
    return data

# Mappa per lanciare i giochi tramite i protocolli nativi di Steam, Battle.net e Riot Client
GAMES_MAP = {
    "cs2": "steam://rungameid/730",
    "counter strike": "steam://rungameid/730",
    "cs go": "steam://rungameid/730",
    "dota 2": "steam://rungameid/570",
    "dota": "steam://rungameid/570",
    "cyberpunk": "steam://rungameid/1091500",
    "cyberpunk 2077": "steam://rungameid/1091500",
    "gta 5": "steam://rungameid/271590",
    "gta v": "steam://rungameid/271590",
    "apex legends": "steam://rungameid/1172470",
    "apex": "steam://rungameid/1172470",
    "diablo 4": "battlenet://fen",
    "diablo iv": "battlenet://fen",
    "diablo": "battlenet://fen",
    "overwatch 2": "battlenet://pro",
    "overwatch": "battlenet://pro",
    "hearthstone": "battlenet://wtr",
    "world of warcraft": "battlenet://wow",
    "wow": "battlenet://wow",
    "valorant": "riotclient://launch-app/valorant"
}

# URL dei server per verificare lo stato di funzionamento
SERVER_URLS = {
    "riot games": "https://status.riotgames.com",
    "riot": "https://status.riotgames.com",
    "valorant": "https://status.riotgames.com",
    "league of legends": "https://status.riotgames.com",
    "lol": "https://status.riotgames.com",
    "steam": "https://store.steampowered.com",
    "epic": "https://status.epicgames.com",
    "epic games": "https://status.epicgames.com",
    "battle.net": "https://status.epicgames.com",
    "blizzard": "https://us.battle.net",
    "playstation": "https://status.playstation.com",
    "xbox": "https://support.xbox.com/xbox-live-status"
}

# Traduzione descrizioni wttr.in
CONDITIONS_MAP = {
    "sunny": "soleggiato",
    "clear": "sereno",
    "partly cloudy": "parzialmente nuvoloso",
    "cloudy": "nuvoloso",
    "overcast": "coperto",
    "mist": "foschia",
    "fog": "nebbia",
    "patchy rain nearby": "pioggia intermittente nelle vicinanze",
    "patchy rain possible": "possibilità di pioggia intermittente",
    "patchy snow possible": "possibilità di neve intermittente",
    "patchy sleet possible": "possibilità di nevischio intermittente",
    "patchy freezing drizzle possible": "possibilità di pioviggine gelida intermittente",
    "thundery outbreaks possible": "possibili rovesci temporaleschi",
    "blowing snow": "neve soffiata",
    "blizzard": "tormenta di neve",
    "freezing fog": "nebbia gelida",
    "patchy light drizzle": "pioviggine leggera a tratti",
    "light drizzle": "pioviggine leggera",
    "freezing drizzle": "pioviggine gelida",
    "heavy freezing drizzle": "forte pioviggine gelida",
    "patchy light rain": "pioggia leggera a tratti",
    "light rain": "pioggia leggera",
    "moderate rain at times": "pioggia moderata a tratti",
    "moderate rain": "pioggia moderata",
    "heavy rain at times": "forte pioggia a tratti",
    "heavy rain": "forte pioggia",
    "light freezing rain": "pioggia gelida leggera",
    "moderate or heavy freezing rain": "pioggia gelida moderata o forte",
    "light sleet": "nevischio leggero",
    "moderate or heavy sleet": "nevischio moderato o forte",
    "patchy light snow": "neve leggera a tratti",
    "light snow": "neve leggera",
    "patchy moderate snow": "neve moderata a tratti",
    "moderate snow": "neve moderata",
    "patchy heavy snow": "forte neve a tratti",
    "heavy snow": "forte neve",
    "ice pellets": "palline di ghiaccio",
    "light rain shower": "rovesci di pioggia leggera",
    "moderate or heavy rain shower": "rovesci di pioggia moderati o forti",
    "torrential rain shower": "rovesci di pioggia torrenziali",
    "light sleet showers": "rovesci di nevischio leggero",
    "moderate or heavy sleet showers": "rovesci di nevischio moderati o forti",
    "light snow showers": "rovesci di neve leggera",
    "moderate or heavy snow showers": "rovesci di neve moderati o forti",
    "light showers of ice pellets": "leggeri rovesci di palline di ghiaccio",
    "moderate or heavy showers of ice pellets": "moderati o forti rovesci di palline di ghiaccio",
    "patchy light rain with thunder": "pioggia leggera a tratti con tuoni",
    "moderate or heavy rain with thunder": "pioggia moderata o forte con tuoni",
    "patchy light snow with thunder": "neve leggera a tratti con tuoni",
    "moderate or heavy snow with thunder": "neve moderata o forte con tuoni"
}

def translate_condition(cond: str) -> str:
    cond_lower = cond.lower().strip()
    return CONDITIONS_MAP.get(cond_lower, cond)

def apri_app_locale(app_name: str) -> bool:
    """Tenta di aprire un'applicazione locale o un protocollo Windows."""
    APP_PROTOCOLS = {
        "whatsapp": "whatsapp:",
        "discord": "discord:",
        "spotify": "spotify:",
        "battle.net": "battlenet://",
        "battlenet": "battlenet://",
        "calcolatrice": "calc",
        "blocco note": "notepad",
        "paint": "mspaint"
    }
    
    app_clean = app_name.lower().strip()
    if app_clean in APP_PROTOCOLS:
        cmd = APP_PROTOCOLS[app_clean]
        try:
            if cmd.endswith(":") or "://" in cmd:
                logger.info(f"Avvio del protocollo Windows: {cmd}")
                webbrowser.open(cmd)
                return True
            else:
                logger.info(f"Avvio dell'eseguibile di sistema: {cmd}")
                subprocess.Popen([cmd])
                return True
        except FileNotFoundError:
            logger.warning(f"File non trovato per l'eseguibile registrato: {cmd}")
        except Exception as e:
            logger.error(f"Errore nel lanciare '{app_name}' tramite mappatura locale: {e}")
            
    try:
        clean_name = app_clean.replace(" ", "")
        subprocess.Popen([clean_name])
        logger.info(f"Avviato con successo l'eseguibile sconosciuto: {clean_name}")
        return True
    except FileNotFoundError:
        logger.debug(f"Eseguibile '{app_clean}' non trovato nel PATH di Windows.")
    except Exception as e:
        logger.debug(f"Impossibile avviare '{app_clean}': {e}")
        
    return False

def play_track_real_spotify(query: str) -> tuple[bool, str, str]:
    """Tenta di riprodurre un brano tramite le API reali di Spotify usando la libreria spotipy."""
    config = load_config()
    sp_id = config.get("spotify_client_id", "").strip()
    sp_secret = config.get("spotify_client_secret", "").strip()
    sp_redirect = config.get("spotify_redirect_uri", "").strip()
    
    if not (sp_id and sp_secret and sp_redirect):
        return False, "", ""
        
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
        
        logger.info("Inizializzazione Spotipy OAuth...")
        scope = "user-modify-playback-state user-read-playback-state"
        
        auth_manager = SpotifyOAuth(
            client_id=sp_id,
            client_secret=sp_secret,
            redirect_uri=sp_redirect,
            scope=scope,
            open_browser=True
        )
        
        sp = spotipy.Spotify(auth_manager=auth_manager)
        logger.info(f"Ricerca traccia su Spotify per: {query}")
        results = sp.search(q=query, type='track', limit=1)
        tracks = results.get('tracks', {}).get('items', [])
        
        if not tracks:
            return True, f"Nessun brano trovato su Spotify per: '{query}'", "Non ho trovato questa canzone su Spotify."
            
        track = tracks[0]
        track_uri = track['uri']
        track_name = track['name']
        artist_name = track['artists'][0]['name']
        
        try:
            sp.start_playback(uris=[track_uri])
            return True, f"Riproduzione avviata: '{track_name}' di {artist_name} su Spotify (API).", f"Riproduco {track_name} di {artist_name}."
        except spotipy.exceptions.SpotifyException as e:
            logger.warning(f"Errore di riproduzione diretta: {e}. Tento fallback sui dispositivi...")
            devices = sp.devices().get('devices', [])
            if devices:
                device_id = devices[0]['id']
                device_name = devices[0]['name']
                sp.start_playback(device_id=device_id, uris=[track_uri])
                return True, f"Riproduzione forzata su dispositivo '{device_name}': '{track_name}' di {artist_name}.", f"Riproduco {track_name} di {artist_name} su {device_name}."
            else:
                return True, (
                    "Impossibile riprodurre: nessun dispositivo Spotify attivo rilevato.\n"
                    "Per favore, apri Spotify sul computer o telefono e riprova."
                ), "Non ho trovato nessun dispositivo attivo su Spotify. Apri l'applicazione."
                
    except Exception as e:
        logger.error(f"Errore durante l'uso delle API di Spotify: {e}")
        return True, f"Errore API Spotify: {e}\nAssicurati che ID, Secret e Redirect URI siano corretti nelle impostazioni.", "Errore di connessione con le API di Spotify."

def generate_secure_password(length: int = 16) -> str:
    """Genera una password casuale sicura contenente maiuscole, minuscole, numeri e simboli."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{}|;:,.<>?"
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in password)
                and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password)
                and any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?" for c in password)):
            return password

def adjust_volume(change_percent: int) -> tuple[bool, str, str]:
    """Modifica il volume master di Windows in modo relativo."""
    try:
        volume = AudioUtilities.GetSpeakers().EndpointVolume
        current_scalar = volume.GetMasterVolumeLevelScalar()
        current_percent = current_scalar * 100.0
        new_percent = current_percent + change_percent
        new_percent = max(0.0, min(100.0, new_percent))
        
        volume.SetMute(0, None)
        volume.SetMasterVolumeLevelScalar(new_percent / 100.0, None)
        
        direction = "alzato" if change_percent > 0 else "abbassato"
        chat_msg = f"Volume {direction} del {abs(change_percent)}%. Livello attuale: {int(new_percent)}%."
        voice_msg = f"Ho {direction} il volume. Ora è al {int(new_percent)} percento."
        return True, chat_msg, voice_msg
    except Exception as e:
        logger.error(f"Errore regolazione volume: {e}")
        return True, f"Errore nella regolazione del volume di sistema: {e}", "Non sono riuscito a regolare il volume."

def set_volume(target_percent: int) -> tuple[bool, str, str]:
    """Imposta il volume master di Windows ad una percentuale specifica."""
    try:
        volume = AudioUtilities.GetSpeakers().EndpointVolume
        target_percent = max(0.0, min(100.0, target_percent))
        
        volume.SetMute(0, None)
        volume.SetMasterVolumeLevelScalar(target_percent / 100.0, None)
        
        chat_msg = f"Volume di sistema impostato al {target_percent}%."
        voice_msg = f"Volume impostato al {target_percent} percento."
        return True, chat_msg, voice_msg
    except Exception as e:
        logger.error(f"Errore impostazione volume: {e}")
        return True, f"Errore nell'impostare il volume di sistema: {e}", "Non sono riuscito a impostare il volume."

def mute_system_volume() -> tuple[bool, str, str]:
    """Attiva lo stato Muto per il volume di Windows."""
    try:
        volume = AudioUtilities.GetSpeakers().EndpointVolume
        volume.SetMute(1, None)
        return True, "Volume di sistema mutato.", "Ho messo il volume in muto."
    except Exception as e:
        logger.error(f"Errore mutamento volume: {e}")
        return True, f"Errore nel silenziare il volume: {e}", "Non ho potuto disattivare l'audio."

def empty_recycle_bin() -> tuple[bool, str, str]:
    """Svuota il Cestino di Windows in background."""
    try:
        result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 7)
        if result == 0:
            return True, "Cestino di Windows svuotato con successo.", "Ho svuotato il cestino."
        else:
            return True, "Il cestino è già vuoto.", "Il cestino è già vuoto."
    except Exception as e:
        logger.error(f"Errore svuotamento cestino: {e}")
        return True, f"Errore durante lo svuotamento del cestino: {e}", "Non sono riuscito a svuotare il cestino."

def set_screen_brightness(level: int):
    """Regola la luminosità dello schermo tramite PowerShell (WMI)."""
    try:
        level = max(0, min(100, level))
        # Utilizza Get-CimInstance che è lo standard per i sistemi Windows recenti
        cmd = f"(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods).WmiSetBrightness(1, {level})"
        subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, timeout=2.0, creationflags=subprocess.CREATE_NO_WINDOW)
        logger.info(f"Luminosità dello schermo impostata al {level}%.")
    except Exception as e:
        logger.error(f"Errore nella regolazione della luminosità: {e}")

def trigger_discord_call() -> tuple[bool, str, str]:
    """Simula la pressione dei tasti Ctrl+Shift+Alt+J per far entrare l'utente in chiamata Discord."""
    try:
        from pynput.keyboard import Key, Controller
        import time
        keyboard = Controller()
        
        # Simula la combinazione ctrl+shift+alt+j
        with keyboard.pressed(Key.ctrl), keyboard.pressed(Key.shift), keyboard.pressed(Key.alt):
            keyboard.press('j')
            time.sleep(0.02)
            keyboard.release('j')
            
        return True, "Eseguo: Connessione al canale Discord...", "Connessione Discord inviata."
    except Exception as e:
        logger.error(f"Errore nella simulazione della macro Discord: {e}")
        return True, f"Errore nell'esecuzione della macro Discord: {e}", "Errore macro."

def send_background_key(window_title: str, key_code: int) -> bool:
    """
    Invia un messaggio WM_KEYDOWN alla finestra con il titolo specificato (anche se in background),
    utilizzando win32gui.PostMessage per non rubare il focus.
    """
    try:
        import win32gui
        import win32con
        import time
        
        hwnd = win32gui.FindWindow(None, window_title)
        if not hwnd:
            # Cerca per corrispondenza parziale
            def enum_windows_callback(h, hwnds_list):
                if win32gui.IsWindowVisible(h):
                    title = win32gui.GetWindowText(h)
                    if window_title.lower() in title.lower():
                        hwnds_list.append(h)
                return True
                
            hwnds = []
            win32gui.EnumWindows(enum_windows_callback, hwnds)
            if hwnds:
                hwnd = hwnds[0]
                
        if hwnd:
            logger.info(f"Invio tasto {key_code} alla finestra '{win32gui.GetWindowText(hwnd)}' (hwnd: {hwnd}) in background.")
            win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, key_code, 0)
            time.sleep(0.02)
            win32gui.PostMessage(hwnd, win32con.WM_KEYUP, key_code, 0)
            return True
            
        logger.warning(f"Finestra con titolo '{window_title}' non trovata per invio tasto in background.")
        return False
    except Exception as e:
        logger.error(f"Errore nell'inviare il tasto in background: {e}")
        return False

def attiva_profilo(nome_profilo: str) -> tuple[bool, str, str]:
    """Attiva un profilo di automazione (Focus, Gaming o Notte) configurando a runtime i parametri associati."""
    config = load_config()
    nome_clean = nome_profilo.lower().strip()
    
    if "gaming" in nome_clean:
        config["active_profile"] = "Gaming"
        config["focus_mode_active"] = False
        save_config(config)
        
        # Imposta il volume master al volume gaming (40% o quello dello slider)
        gaming_vol_val = config.get("gaming_volume", 0.40)
        gaming_vol_pct = int(gaming_vol_val * 100)
        set_volume(gaming_vol_pct)
        
        ram_report = ""
        if config.get("gaming_optimize_ram", True):
            gc.collect()
            ram = psutil.virtual_memory()
            ram_report = f"Memoria RAM ottimizzata (Uso attuale: {ram.percent}%)."
        
        launchers = []
        if config.get("gaming_open_launchers", True):
            try:
                os.startfile("steam://")
                launchers.append("Steam")
            except Exception:
                pass
            try:
                os.startfile("battlenet://")
                launchers.append("Battle.net")
            except Exception:
                pass
                
        # --- Advanced Gaming Features ---
        if config.get("gaming_high_performance", True):
            try:
                subprocess.run("powercfg /S SCHEME_MIN", shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
                chat_msg_power = "- Power Plan: Prestazioni Eccellenti"
            except Exception:
                chat_msg_power = ""
        else:
            chat_msg_power = ""
            
        closed_browsers = 0
        if config.get("gaming_kill_browsers", False):
            target_browsers = ["chrome.exe", "msedge.exe", "firefox.exe", "opera.exe"]
            for proc in psutil.process_iter(['name']):
                try:
                    if proc.info['name'] and proc.info['name'].lower() in target_browsers:
                        proc.kill()
                        closed_browsers += 1
                except Exception:
                    pass
        # ---------------------------------
        
        chat_msg = f"🎮 **Profilo Gaming Attivato**\n- Volume master impostato al {gaming_vol_pct}%\n- Comportamento Gemini: Sintetico/Essenziale\n- {ram_report}"
        if chat_msg_power:
            chat_msg += f"\n{chat_msg_power}"
        if closed_browsers > 0:
            chat_msg += f"\n- Browser forzatamente chiusi: {closed_browsers}"
        if launchers:
            chat_msg += f"\n- Launcher avviati: {', '.join(launchers)}"
            
        voice_msg = f"Profilo Gaming attivato. Ho impostato il volume al {gaming_vol_pct} percento ed attivato la modalità sintetica."
        return True, chat_msg, voice_msg
        
    elif "focus" in nome_clean or "studio" in nome_clean:
        config["active_profile"] = "Focus"
        config["focus_mode_active"] = True
        save_config(config)
        
        closed = []
        if config.get("focus_close_apps", True):
            DISTRACTING_APPS = ["discord.exe", "steam.exe", "battle.net.exe", "battlenet.exe", "epicgameslauncher.exe"]
            for proc in psutil.process_iter(['name']):
                try:
                    name = proc.info['name']
                    if name and name.lower() in DISTRACTING_APPS:
                        proc.terminate()
                        closed.append(name)
                except Exception:
                    pass
                    
        chat_msg = "🎯 **Profilo Focus / Studio Attivato**\n- Risposte vocali (TTS) disattivate\n- Notifiche silenziate"
        if closed:
            chat_msg += f"\n- App distractive chiuse: {', '.join(set(closed))}"
            
        # --- Advanced Focus Features ---
        if config.get("focus_pomodoro", False):
            def pomodoro_thread():
                import time
                time.sleep(25 * 60)
                try:
                    from src.utils import play_beep
                    play_beep()
                    from plyer import notification
                    notification.notify(title="Pomodoro", message="I 25 minuti di focus sono terminati. Fai una pausa!", timeout=10)
                except Exception:
                    pass
            threading.Thread(target=pomodoro_thread, daemon=True).start()
            chat_msg += "\n- Timer Pomodoro (25m) avviato"
            
        if config.get("focus_lofi", False):
            import webbrowser
            try:
                webbrowser.open("https://www.youtube.com/watch?v=jfKfPfyJRdk")
                chat_msg += "\n- Playlist Lo-Fi aperta nel browser"
            except Exception:
                pass
        # -------------------------------
            
        voice_msg = "Profilo Focus attivato. Da questo momento sarò silenzioso per non disturbare lo studio."
        return True, chat_msg, voice_msg

    elif "notte" in nome_clean or "relax" in nome_clean:
        config["active_profile"] = "Notte"
        config["focus_mode_active"] = False
        save_config(config)
        
        # Imposta luminosità e volume per la notte
        night_vol = int(float(config.get("night_volume", 0.15)) * 100)
        night_bright = int(config.get("night_brightness", 15))
        
        set_volume(night_vol)
        set_screen_brightness(night_bright)
        
        chat_msg = f"🌙 **Profilo Notte / Relax Attivato**\n- Luminosità dello schermo ridotta al {night_bright}%\n- Volume master ridotto al {night_vol}%\n- Risposte di Gemini calme e pacate"
        
        # --- Advanced Night Features ---
        sleep_timer = config.get("night_sleep_timer", "Mai")
        if sleep_timer != "Mai":
            try:
                min_map = {"30 Minuti": 1800, "60 Minuti": 3600, "120 Minuti": 7200}
                if sleep_timer in min_map:
                    secs = min_map[sleep_timer]
                    subprocess.run(f"shutdown /s /t {secs}", shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    chat_msg += f"\n- Autospegnimento programmato tra {sleep_timer.split()[0]} minuti"
            except Exception:
                pass
                
        if config.get("night_blue_light", True):
            try:
                ps_script = 'Set-ItemProperty -Path "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\CloudStore\\Store\\DefaultAccount\\Current\\default$windows.data.bluelightreduction.bluelightreductionstate\\windows.data.bluelightreduction.bluelightreductionstate" -Name "Data" -Value ([byte[]](0x02,0x00,0x00,0x00,0x54,0x83,0x08,0x4a,0x03,0xba,0xd2,0x01,0x00,0x00,0x00,0x00,0x43,0x42,0x01,0x00,0x10,0x00,0xd0,0x0a,0x02,0xc6,0x14,0xb8,0x8e,0x9d,0xd0,0xb4,0xc0,0xae,0xe9,0x01,0x00))'
                subprocess.run(["powershell", "-Command", ps_script], shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
                chat_msg += "\n- Filtro Luce Blu abilitato (Registro)"
            except Exception:
                pass
        # -------------------------------

        voice_msg = "Profilo Notte attivato. Ho ridotto la luminosità e il volume per il tuo relax. Riposati pure."
        return True, chat_msg, voice_msg
        
    return True, f"Profilo '{nome_profilo}' non riconosciuto.", f"Non conosco il profilo {nome_profilo}."

def disattiva_profili() -> tuple[bool, str, str]:
    """Disattiva i profili attivi ripristinando le impostazioni standard."""
    config = load_config()
    config["active_profile"] = "Nessuno"
    config["focus_mode_active"] = False
    save_config(config)
    
    # Ripristina volume e luminosità standard
    std_vol = int(float(config.get("volume", 0.55)) * 100)
    std_bright = int(config.get("std_brightness", 80))
    
    set_volume(std_vol)
    set_screen_brightness(std_bright)
    
    chat_msg = f"🌿 **Profilo Standard Ripristinato**\n- Volume master ripristinato al {std_vol}%\n- Luminosità ripristinata al {std_bright}%\n- Risposte di Gemini standard"
    
    # --- Reset Advanced Features ---
    try:
        subprocess.run("shutdown /a", shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:
        pass
        
    try:
        subprocess.run("powercfg /S SCHEME_BALANCED", shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:
        pass
    # -------------------------------
    
    voice_msg = "Profili disattivati. Ho ripristinato i valori standard di luminosità e volume."
    return True, chat_msg, voice_msg

def kill_process_by_name(app_name: str) -> tuple[bool, str, str]:
    """Cerca e termina forzatamente i processi associati al nome fornito."""
    app_clean = app_name.lower().strip()
    target = app_clean if app_clean.endswith(".exe") else app_clean + ".exe"
    
    terminated = 0
    for proc in psutil.process_iter(['name', 'pid']):
        try:
            name = proc.info['name']
            if name and (app_clean in name.lower() or name.lower() == target):
                proc.kill()
                terminated += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
            
    if terminated > 0:
        return True, f"Kill Switch: terminati {terminated} processi associati a '{app_name}'.", f"Ho terminato tutti i processi di {app_name}."
    else:
        return True, f"Kill Switch: nessun processo attivo corrispondente a '{app_name}' trovato.", f"Non ho trovato nessun processo attivo per {app_name}."

def launch_game_lobby(game_name: str) -> tuple[bool, str, str]:
    """Avvia le lobby di gioco sfruttando i protocolli di integrazione nativi."""
    game_clean = game_name.lower().strip()
    
    if game_clean in GAMES_MAP:
        uri = GAMES_MAP[game_clean]
        try:
            os.startfile(uri)
            return True, f"Avvio lobby di '{game_name}' tramite protocollo: `{uri}`.", f"Avvio {game_name}."
        except Exception as e:
            logger.error(f"Errore lancio {game_name}: {e}")
            return True, f"Errore nell'aprire la lobby di '{game_name}': {e}", f"Non sono riuscito ad avviare {game_name}."
            
    if "steam" in game_clean:
        try:
            os.startfile("steam://")
            return True, "Apertura di Steam.", "Apro Steam."
        except Exception:
            pass
    elif "battle.net" in game_clean or "battlenet" in game_clean:
        try:
            os.startfile("battlenet://")
            return True, "Apertura di Battle.net.", "Apro Battle net."
        except Exception:
            pass
    elif "epic" in game_clean:
        try:
            os.startfile("com.epicgames.launcher://")
            return True, "Apertura di Epic Games Launcher.", "Apro Epic Games."
        except Exception:
            pass
            
    if apri_app_locale(game_clean):
        return True, f"Avviato eseguibile per il gioco locale: '{game_name}'.", f"Apro {game_name}."
        
    return False, "", ""

def check_server_status(game_name: str) -> tuple[bool, str, str]:
    """Controlla lo stato dei server di gioco inviando richieste di rete di test."""
    name_clean = game_name.lower().strip()
    
    target_url = None
    display_name = game_name.title()
    for key, url in SERVER_URLS.items():
        if key in name_clean or name_clean in key:
            target_url = url
            display_name = key.title()
            break
            
    if not target_url:
        target_url = "https://www.google.com"
        
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.head(target_url, headers=headers, timeout=3.0)
        if res.status_code < 400:
            return True, f"I server di **{display_name}** sembrano **ONLINE** ({target_url}). HTTP Status: {res.status_code}.", f"I server di {display_name} sono online e funzionano."
        else:
            return True, f"I server di **{display_name}** rispondono ma segnalano anomalie (HTTP Status: {res.status_code}).", f"I server di {display_name} potrebbero riscontrare dei problemi temporanei."
    except Exception as e:
        logger.warning(f"Errore nel pinging del server {display_name}: {e}")
        return True, f"I server di **{display_name}** sembrano **OFFLINE** o irraggiungibili. Errore connessione.", f"I server di {display_name} sembrano non rispondere. Potrebbero essere offline."

def organize_downloads() -> tuple[bool, str, str]:
    """Scansiona e riorganizza la cartella download in sottocartelle in base alle estensioni."""
    try:
        downloads_path = Path(os.environ["USERPROFILE"]) / "Downloads"
        if not downloads_path.exists():
            return True, "Cartella Download non trovata nel profilo utente.", "La cartella dei download non esiste."
            
        CATEGORIES = {
            "Installers": [".exe", ".msi", ".bat", ".cmd"],
            "Immagini": [".jpg", ".jpeg", ".png", ".gif", ".svg", ".bmp", ".webp", ".ico"],
            "Documenti": [".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".txt", ".csv", ".epub"],
            "Archivi": [".zip", ".rar", ".7z", ".tar", ".gz", ".iso"],
            "Audio": [".mp3", ".wav", ".flac", ".ogg", ".m4a"],
            "Video": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv"]
        }
        
        moved_counts = {}
        total_moved = 0
        
        for item in downloads_path.iterdir():
            if item.is_file():
                ext = item.suffix.lower()
                target_folder = None
                
                for folder, extensions in CATEGORIES.items():
                    if ext in extensions:
                        target_folder = folder
                        break
                        
                if target_folder:
                    dest_dir = downloads_path / target_folder
                    dest_dir.mkdir(exist_ok=True)
                    
                    dest_path = dest_dir / item.name
                    counter = 1
                    while dest_path.exists():
                        dest_path = dest_dir / f"{item.stem}_{counter}{ext}"
                        counter += 1
                        
                    shutil.move(str(item), str(dest_path))
                    moved_counts[target_folder] = moved_counts.get(target_folder, 0) + 1
                    total_moved += 1
                    
        if total_moved > 0:
            summary_str = ", ".join([f"{val} in {key}" for key, val in moved_counts.items()])
            return True, f"Organizzazione completata. Spostati {total_moved} file:\n{summary_str}", f"Ho riordinato i file nei download, spostandone in totale {total_moved}."
        else:
            return True, "La cartella Download è già ordinata, nessun file da spostare.", "La cartella download è già in ordine."
            
    except Exception as e:
        logger.error(f"Errore organizzatore download: {e}")
        return True, f"Errore nell'organizzare la cartella download: {e}", "Non sono riuscito ad organizzare i download."

def search_local_file(file_query: str) -> tuple[bool, str, str]:
    """Esegue una scansione veloce per trovare un file locale in Desktop, Documenti e Download."""
    file_query = file_query.strip().lower()
    search_dirs = [
        Path(os.environ["USERPROFILE"]) / "Desktop",
        Path(os.environ["USERPROFILE"]) / "Documents",
        Path(os.environ["USERPROFILE"]) / "Downloads"
    ]
    
    results = []
    max_results = 5
    
    for base_dir in search_dirs:
        if not base_dir.exists():
            continue
        try:
            for path in base_dir.rglob("*"):
                if len(results) >= max_results:
                    break
                try:
                    depth = len(path.relative_to(base_dir).parts)
                    if depth > 3:
                        continue
                except ValueError:
                    continue
                    
                if path.is_file() and file_query in path.name.lower():
                    results.append(path)
        except Exception:
            pass
            
    if results:
        chat_lines = []
        for p in results:
            uri = p.absolute().as_uri()
            chat_lines.append(f"- [{p.name}]({uri}) in `{p.parent}`")
        
        chat_resp = "Ho individuato i seguenti file:\n" + "\n".join(chat_lines)
        voice_resp = f"Ho trovato {len(results)} file corrispondenti."
        return True, chat_resp, voice_resp
    else:
        return True, f"Nessun file contenente '{file_query}' trovato su Desktop, Documenti o Download (limite 3 livelli).", f"Nessun file corrispondente a {file_query} trovato."

def extract_latest_download() -> tuple[bool, str, str]:
    """Estrae l'ultimo file ZIP modificato presente nella cartella dei Download."""
    try:
        downloads_path = Path(os.environ["USERPROFILE"]) / "Downloads"
        if not downloads_path.exists():
            return True, "Cartella Download non trovata.", "La cartella download non esiste."
            
        archives = []
        for item in downloads_path.iterdir():
            if item.is_file() and item.suffix.lower() == ".zip":
                archives.append((item, item.stat().st_mtime))
                
        if not archives:
            return True, "Nessun file ZIP trovato nella cartella Download.", "Non ho trovato nessun file zip recente da estrarre."
            
        archives.sort(key=lambda x: x[1], reverse=True)
        latest_archive, _ = archives[0]
        
        dest_dir = downloads_path / latest_archive.stem
        counter = 1
        while dest_dir.exists():
            dest_dir = downloads_path / f"{latest_archive.stem}_{counter}"
            counter += 1
            
        dest_dir.mkdir(exist_ok=True)
        
        with zipfile.ZipFile(latest_archive, 'r') as zip_ref:
            zip_ref.extractall(dest_dir)
            
        return True, f"Estratto l'archivio `{latest_archive.name}` nella cartella:\n`{dest_dir}`", f"Ho estratto {latest_archive.name} in una cartella dedicata."
    except Exception as e:
        logger.error(f"Errore estrazione ZIP: {e}")
        return True, f"Errore durante l'estrazione dell'ultimo ZIP: {e}", "Non sono riuscito a scompattare l'ultimo archivio."

def get_gpu_status():
    """Tenta di estrarre l'uso e la temperatura della GPU NVIDIA tramite nvidia-smi."""
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=1.5
        )
        if res.returncode == 0:
            parts = res.stdout.strip().split(",")
            if len(parts) >= 2:
                util = int(parts[0].strip())
                temp = int(parts[1].strip())
                return util, temp
    except Exception:
        pass
    return None, None

def get_system_resources_status() -> tuple[bool, str, str]:
    """Rileva in tempo reale l'uso di CPU, RAM e GPU del computer."""
    cpu_percent = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory()
    ram_used = ram.used / (1024**3)
    ram_percent = ram.percent
    
    gpu_util, gpu_temp = get_gpu_status()
    
    chat_lines = [
        "📊 **Diagnostica Hardware del Sistema**:",
        f"- **CPU:** {cpu_percent}% di carico di lavoro",
        f"- **RAM:** {ram_percent}% ({ram_used:.1f} GB utilizzati su {ram.total / (1024**3):.1f} GB)"
    ]
    
    voice_msg = f"Stai consumando il {int(cpu_percent)} percento della CPU e {ram_used:.1f} Gigabyte di RAM."
    
    if gpu_util is not None:
        chat_lines.append(f"- **GPU:** {gpu_util}% di carico")
        chat_lines.append(f"- **Temperatura GPU:** {gpu_temp}°C")
        voice_msg += f" La tua scheda video lavora al {gpu_util}% con una temperatura di {gpu_temp} gradi."
        
    chat_resp = "\n".join(chat_lines)
    return True, chat_resp, voice_msg

def get_ip_addresses() -> tuple[bool, str, str]:
    """Rileva e mostra gli indirizzi IP locale e pubblico del PC."""
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = "Rilevamento locale fallito"
        
    try:
        public_ip = requests.get("https://api.ipify.org", timeout=2.0).text.strip()
    except Exception:
        public_ip = "Non rilevato (Offline)"
        
    chat_msg = f"🌐 **Configurazione Indirizzi IP**:\n- **IP Locale:** `{local_ip}`\n- **IP Pubblico:** `{public_ip}`"
    voice_msg = f"Il tuo indirizzo IP locale è {local_ip}."
    return True, chat_msg, voice_msg

def check_port_status(port: int) -> tuple[bool, str, str]:
    """Verifica se una porta di rete specifica sul localhost (127.0.0.1) è aperta o chiusa."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.8)
    result = s.connect_ex(("127.0.0.1", port))
    s.close()
    
    if result == 0:
        return True, f"Diagnostica di rete: la porta `{port}` su localhost (127.0.0.1) è **APERTA** (in ascolto).", f"La porta {port} è aperta."
    else:
        return True, f"Diagnostica di rete: la porta `{port}` su localhost (127.0.0.1) è **CHIUSA** o non in ascolto.", f"La porta {port} è chiusa."

# ==================== NUOVE UTILITIES FASE 3 (To-Do List, Meteo, RSS) ====================

def load_todo() -> list:
    """Carica la todo list locale in memoria da file JSON."""
    if TODO_FILE.exists():
        try:
            with open(TODO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_todo(todo_list: list):
    """Salva su file JSON la todo list corrente."""
    try:
        with open(TODO_FILE, "w", encoding="utf-8") as f:
            json.dump(todo_list, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Errore nel salvare todo_list.json: {e}")

def add_todo_task(task: str) -> str:
    """Aggiunge una nuova attività alla lista delle cose da fare."""
    tasks = load_todo()
    date_str = datetime.datetime.now().strftime("%d/%m/%Y")
    tasks.append({"task": task, "date": date_str})
    save_todo(tasks)
    return f"Attività aggiunta alla To-Do list:\n- **{task}** (il {date_str})"

def get_todo_list_text() -> str:
    """Restituisce il testo strutturato con l'elenco della To-Do list."""
    tasks = load_todo()
    if not tasks:
        return "La tua lista delle cose da fare è vuota."
    lines = ["📝 **To-Do List Attuale**:\n"]
    for idx, t in enumerate(tasks, 1):
        lines.append(f"{idx}. **{t['task']}** (inserita il {t['date']})")
    return "\n".join(lines)

def remove_todo_task(query: str) -> str:
    """Rimuove un'attività dalla To-Do list per testo o per numero di indice."""
    tasks = load_todo()
    if not tasks:
        return "Nessuna attività registrata nella lista."
        
    query_clean = query.strip()
    
    # 1. Rimuove per Indice Numerico (1-based)
    if query_clean.isdigit():
        idx = int(query_clean) - 1
        if 0 <= idx < len(tasks):
            removed = tasks.pop(idx)
            save_todo(tasks)
            return f"Rimossa attività #{idx+1}: **{removed['task']}**."
        else:
            return f"Errore: numero attività #{query_clean} fuori dal range (totale elementi: {len(tasks)})."
            
    # 2. Rimuove per corrispondenza di testo parziale
    for t in tasks:
        if query_clean.lower() in t["task"].lower():
            tasks.remove(t)
            save_todo(tasks)
            return f"Rimossa attività corrispondente: **{t['task']}**."
            
    return f"Nessun elemento corrispondente a '{query_clean}' trovato nella To-Do list."

def check_weather(city: str, tomorrow: bool = False) -> tuple[bool, str, str]:
    """Recupera le condizioni meteo da wttr.in per la città specificata."""
    city_encoded = urllib.parse.quote(city.strip())
    url = f"https://wttr.in/{city_encoded}?format=j1"
    
    try:
        res = requests.get(url, timeout=4.0)
        if res.status_code != 200:
            return True, f"Impossibile trovare dettagli meteo per '{city}'.", "Non ho trovato dati meteo per questa città."
            
        data = res.json()
        current = data['current_condition'][0]
        temp = current['temp_C']
        feels = current['FeelsLikeC']
        humidity = current['humidity']
        wind = current['windspeedKmph']
        desc = current['weatherDesc'][0]['value']
        desc_it = translate_condition(desc)
        
        area_name = data['nearest_area'][0]['areaName'][0]['value'].title()
        
        if tomorrow:
            day_data = data['weather'][1]
            max_temp = day_data['maxtempC']
            min_temp = day_data['mintempC']
            tom_desc = day_data['hourly'][4]['weatherDesc'][0]['value']
            tom_desc_it = translate_condition(tom_desc)
            
            chat_msg = (
                f"📅 **Meteo di Domani a {area_name}**:\n"
                f"- **Previsione:** {tom_desc_it.title()}\n"
                f"- **Temperatura Max:** {max_temp}°C\n"
                f"- **Temperatura Min:** {min_temp}°C"
            )
            voice_msg = f"Domani a {area_name} le previsioni indicano {tom_desc_it} con una temperatura massima di {max_temp} gradi e minima di {min_temp} gradi."
        else:
            chat_msg = (
                f"☀️ **Condizioni Meteo a {area_name}**:\n"
                f"- **Meteo:** {desc_it.title()}\n"
                f"- **Temperatura:** {temp}°C (Percepita: {feels}°C)\n"
                f"- **Umidità:** {humidity}%\n"
                f"- **Vento:** {wind} km/h"
            )
            voice_msg = f"Attualmente a {area_name} c'è {desc_it} con {temp} gradi. La temperatura percepita è di {feels} gradi."
            
        return True, chat_msg, voice_msg
    except Exception as e:
        logger.error(f"Errore WTTR API: {e}")
        return True, f"Errore nel rilevare il meteo per '{city}': {e}", "Non sono riuscito a contattare il servizio meteo."

def get_tech_news() -> tuple[bool, str, str]:
    """Legge i feed RSS tecnologici di ANSA ed estrae le prime 3 notizie principali."""
    import feedparser
    url = "https://www.ansa.it/sito/notizie/tecnologia/tecnologia_rss.xml"
    
    try:
        feed = feedparser.parse(url)
        if not feed.entries:
            return True, "Nessuna notizia rilevata nei Feed RSS.", "Non ci sono notizie tech disponibili."
            
        chat_lines = ["📰 **Notizie Tecnologiche della Giornata (ANSA)**:\n"]
        voice_titles = []
        
        for idx, entry in enumerate(feed.entries[:3], 1):
            title = entry.title
            link = entry.link
            chat_lines.append(f"{idx}. **[{title}]({link})**")
            voice_titles.append(title)
            
        chat_msg = "\n".join(chat_lines)
        voice_msg = f"Ecco le ultime notizie tecnologiche da ANSA. Primo: {voice_titles[0]}. Secondo: {voice_titles[1]}. Terzo: {voice_titles[2]}."
        return True, chat_msg, voice_msg
    except Exception as e:
        logger.error(f"Errore lettura Feed RSS: {e}")
        return True, f"Errore nel caricamento delle notizie dal Feed RSS: {e}", "Non sono riuscito a leggere le ultime notizie."

# ==================== PARSER PRINCIPALE COMANDI LOCALI ====================

def parse_local_command(text: str) -> tuple[bool, str, str]:
    """
    Analizza il testo alla ricerca di comandi locali.
    Ritorna (is_command, chat_response, voice_response).
    """
    text_clean = text.lower().strip()
    
    # ----------------- SHORTCUT MULTIMEDIALI RAPIDI (No Gemini) -----------------
    if any(k in text_clean for k in ["metti in pausa", "stoppa la musica", "ferma la musica", "riprendi la musica", "metti play"]):
        import pyautogui
        pyautogui.press('playpause')
        return True, "Fatto. ⏸️", "Fatto."
    if any(k in text_clean for k in ["prossima canzone", "canzone successiva", "metti la prossima", "skippa canzone", "salta traccia"]):
        import pyautogui
        pyautogui.press('nexttrack')
        return True, "Skippata. ⏭️", "Canzone saltata."
    if any(k in text_clean for k in ["canzone precedente", "rimetti da capo", "traccia precedente"]):
        import pyautogui
        pyautogui.press('prevtrack')
        return True, "Indietro. ⏮️", "Fatto."
    if any(k in text_clean for k in ["abbassa il volume di spotify", "abbassa spotify", "spotify più basso"]):
        import pyautogui
        for _ in range(5): pyautogui.press('volumedown') # Abbassa di 5 step il volume master per coprire spotify
        return True, "Volume abbassato. 🔉", "Volume ridotto."

    # ----------------- SYSTEM STATE RAPIDI (No Gemini) -----------------
    if any(k in text_clean for k in ["blocca il pc", "blocca il computer", "chiudi a chiave"]):
        import ctypes
        ctypes.windll.user32.LockWorkStation()
        return True, "Computer bloccato. 🔒", "PC bloccato."
    if any(k in text_clean for k in ["mostra il desktop", "abbassa le finestre", "nascondi tutto"]):
        import pyautogui
        pyautogui.hotkey('win', 'd')
        return True, "Desktop mostrato. 🖥️", "Finestre abbassate."
    if any(k in text_clean for k in ["svuota il cestino", "butta l'immondizia", "pulisci il cestino"]):
        return empty_recycle_bin()

    # ----------------- APP LAUNCHERS (Dizionario Esteso) -----------------
    fast_apps = {
        "apri blocco note": "notepad",
        "apri calcolatrice": "calc",
        "apri esplora file": "explorer",
        "apri impostazioni": "ms-settings:",
        "apri gestione attività": "taskmgr",
        "apri prompt": "cmd",
        "apri youtube": "https://www.youtube.com",
        "apri google": "https://www.google.com",
        "apri chatgpt": "https://chatgpt.com",
        "apri netflix": "https://www.netflix.com",
        "apri twitch": "https://www.twitch.tv",
        "apri amazon": "https://www.amazon.it",
        "apri whatsapp": "whatsapp:",
        "apri spotify": "spotify:"
    }
    for trigger, target in fast_apps.items():
        if trigger in text_clean:
            import os, webbrowser
            if target.startswith("http"):
                webbrowser.open(target)
            else:
                os.system(f"start {target}")
            return True, f"Apertura istantanea di {trigger.replace('apri ', '')}... 🚀", "Fatto."

    # ----------------- CLIPBOARD AI ANALYZER -----------------
    if any(k in text_clean for k in ["analizza appunti", "spiegami gli appunti", "spiegami gli appunti di windows", "analizza gli appunti", "analizza il clipboard", "spiega appunti"]):
        return True, "clipboard_analyze_trigger:", ""

    
    # ----------------- 1. INTEGRATIVI AI MULTIMODALE FASE 3 E RPA -----------------
    if any(k in text_clean for k in ["esegui automazione", "esegui automazioni", "fai questo per me", "automazione", "automazioni"]):
        # Estrai solo la parte successiva alla parola trigger, per semplificare
        prompt = text.replace("esegui automazioni", "").replace("esegui automazione", "").replace("fai questo per me", "").replace("automazioni", "").replace("automazione", "").strip()
        if prompt.startswith(":"): prompt = prompt[1:].strip()
        return True, f"rpa_trigger:{prompt}", ""

    if any(k in text_clean for k in ["guarda qui", "spiegami cosa c'è a schermo", "analizza questo errore", "guarda lo schermo", "analizza lo schermo"]):
        # Rileva prompt aggiuntivo
        prompt = text.strip()
        return True, f"vision_trigger:{prompt}", ""

    if any(k in text_clean for k in ["come sta il pc", "prestazioni", "analisi di sistema", "status pc", "stato del sistema"]):
        return True, "system_diagnostics_trigger:", ""
        
    kill_match = re.search(r'\b(?:chiudi il programma|termina il processo|chiudi|termina l\'app|killa|forza chiusura|killami|termina)\s+(.+)', text_clean)
    if kill_match:
        orig_match = re.search(r'\b(?:chiudi il programma|termina il processo|chiudi|termina l\'app|killa|forza chiusura|killami|termina)\s+(.+)', text, re.IGNORECASE)
        app_name = orig_match.group(1).strip() if orig_match else kill_match.group(1).strip()
        if app_name and app_name.lower() not in ["", "tutto", "omnimind"]:
            return True, f"process_kill_trigger:{app_name}", ""
        
    doc_match = re.search(r'\b(?:riassumi il documento|leggi questo file|riassumi il file|leggi il file)\s+(.+)', text_clean)
    if doc_match:
        orig_match = re.search(r'\b(?:riassumi il documento|leggi questo file|riassumi il file|leggi il file)\s+(.+)', text, re.IGNORECASE)
        path = orig_match.group(1).strip() if orig_match else doc_match.group(1).strip()
        return True, f"doc_summary_trigger:{path}", ""
        
    gaming_advice_match = re.search(r'\b(?:consigliami una build per|come countero|build per|consigli per)\s+(.+)', text_clean)
    if gaming_advice_match:
        orig_match = re.search(r'\b(?:consigliami una build per|come countero|build per|consigli per)\s+(.+)', text, re.IGNORECASE)
        query = orig_match.group(0).strip() if orig_match else text
        return True, f"gaming_expert_trigger:{query}", ""
        
    # Traduttore (traduci in [lingua]: [frase])
    trans_match1 = re.search(r'traduci in\s+([a-zA-Z\s]+?):\s*(.+)', text, re.IGNORECASE)
    if trans_match1:
        lang = trans_match1.group(1).strip()
        phrase = trans_match1.group(2).strip()
        return True, f"translate_trigger:{lang}:{phrase}", ""
        
    # Traduttore (come si dice [frase] in [lingua])
    trans_match2 = re.search(r'come si dice\s+(.+?)\s+in\s+([a-zA-Z\s]+)', text, re.IGNORECASE)
    if trans_match2:
        phrase = trans_match2.group(1).strip()
        lang = trans_match2.group(2).strip()
        return True, f"translate_trigger:{lang}:{phrase}", ""

    # ----------------- 2. UTILITY TEMPO MULTI-THREAD FASE 3 (Timer e Sveglie) -----------------
    timer_match = re.search(r'\btimer\b\s+(?:di|da|per)?\s*(\d+)\s*(second|minut|or)\w*(?:\s+(?:per|chiamato|di)\s+(.+))?', text_clean)
    if timer_match:
        val = int(timer_match.group(1))
        unit = timer_match.group(2)
        label = timer_match.group(3).strip() if timer_match.group(3) else "Timer"
        seconds = val
        if "minut" in unit:
            seconds = val * 60
        elif "or" in unit:
            seconds = val * 3600
        label_clean = label.replace(":", "-")
        return True, f"timer_set:{seconds}:{label_clean}", ""
        
    alarm_match = re.search(r'\bsveglia\b\s+(?:alle|per le)?\s*(\d{1,2})[:.](\d{2})(?:\s+(?:per|chiamata|di)\s+(.+))?', text_clean)
    if alarm_match:
        hour = int(alarm_match.group(1))
        minute = int(alarm_match.group(2))
        label = alarm_match.group(3).strip() if alarm_match.group(3) else "Sveglia"
        label_clean = label.replace(":", "-")
        time_str = f"{hour:02d}:{minute:02d}"
        return True, f"alarm_set:{time_str}:{label_clean}", ""

    # ----------------- 3. TO-DO LIST LOCALE FASE 3 -----------------
    todo_add_match = re.search(r'aggiungi\s+(.+?)\s+a(?:l|lle|lla)?\s+(?:cose da fare|to-do list|lista)', text_clean)
    if todo_add_match:
        orig_match = re.search(r'aggiungi\s+(.+?)\s+a(?:l|lle|lla)?\s+(?:cose da fare|to-do list|lista)', text, re.IGNORECASE)
        task = orig_match.group(1).strip() if orig_match else todo_add_match.group(1).strip()
        resp = add_todo_task(task)
        return True, resp, resp
        
    if any(k in text_clean for k in ["mostra la mia lista", "mostra la to-do list", "mostra cose da fare", "cosa ho da fare", "mostra la lista"]):
        resp = get_todo_list_text()
        return True, resp, "Ho mostrato la tua lista delle cose da fare."
        
    todo_rem_match = re.search(r'(?:rimuovi|cancella|elimina)\s+(.+?)\s+da(?:lla|lle)?\s+(?:to-do list|cose da fare|lista)', text_clean)
    if todo_rem_match:
        orig_match = re.search(r'(?:rimuovi|cancella|elimina)\s+(.+?)\s+da(?:lla|lle)?\s+(?:to-do list|cose da fare|lista)', text, re.IGNORECASE)
        query = orig_match.group(1).strip() if orig_match else todo_rem_match.group(1).strip()
        resp = remove_todo_task(query)
        return True, resp, resp

    # ----------------- 4. METEO E NOTIZIE RSS FASE 3 -----------------
    weather_match = re.search(r'(?:che tempo fa a|meteo domani a|meteo a|tempo a)\s+(.+)', text_clean)
    if weather_match:
        orig_match = re.search(r'(?:che tempo fa a|meteo domani a|meteo a|tempo a)\s+(.+)', text, re.IGNORECASE)
        city = orig_match.group(1).strip() if orig_match else weather_match.group(1).strip()
        tomorrow = "domani" in text_clean
        return check_weather(city, tomorrow)
    if any(k in text_clean for k in ["quali sono le ultime notizie tech", "dimmi le notizie del giorno", "notizie del giorno", "tecnologia notizie", "notizie tech", "ultime notizie"]):
        return get_tech_news()

    # ----------------- MACRO DISCORD CANALE VOCALE -----------------
    if any(k in text_clean for k in ["entra in chiamata", "entra su discord", "avvia la call", "connettiti al canale vocale"]):
        return trigger_discord_call()

    # ----------------- 5. GESTIONE PROFILI (Fase 2 / Fase 4) -----------------
    if any(k in text_clean for k in ["ripristina profilo standard", "ripristina standard", "ripristina modalità standard"]):
        return disattiva_profili()

    active_profile_match = re.search(r'(?:attiva|abilita)\s+(?:modalità|profilo)\s+(gaming|gioco|focus|studio|notte|relax)', text_clean)
    if active_profile_match:
        prof = active_profile_match.group(1)
        if prof in ["gaming", "gioco"]:
            return attiva_profilo("gaming")
        elif prof in ["focus", "studio"]:
            return attiva_profilo("focus")
        elif prof in ["notte", "relax"]:
            return attiva_profilo("notte")
            
    disable_profile_match = re.search(r'(?:disattiva|disabilita)\s+(?:modalità|profilo|profili)\s*(gaming|gioco|focus|studio|notte|relax)?', text_clean)
    if disable_profile_match:
        return disattiva_profili()

    # ----------------- 6. DIAGNOSTICA HARDWARE E RETE (Fase 2) -----------------
    if any(k in text_clean for k in ["quanta ram sto usando", "stato cpu", "temperatura hardware", "risorse di sistema", "stato hardware", "consumo risorse"]):
        return get_system_resources_status()
        
    if any(k in text_clean for k in ["qual è il mio ip", "mio ip", "ip pubblico", "ip locale"]):
        return get_ip_addresses()
        
    port_match = re.search(r'(?:controlla porta|verifica porta|controlla la porta|verifica la porta)\s+(\d+)', text_clean)
    if port_match:
        return check_port_status(int(port_match.group(1)))

    # ----------------- 7. ORGANIZZAZIONE E GESTIONE FILE (Fase 2) -----------------
    if any(k in text_clean for k in ["fai ordine nei download", "organizza i download", "pulisci la cartella download", "organizza download"]):
        return organize_downloads()
        
    if any(k in text_clean for k in ["estrai l'ultimo download", "scompatta l'ultimo download", "scompatta ultimo file", "estrai ultimo file"]):
        return extract_latest_download()
        
    find_file_match = re.search(r'(?:cerca il file|trova il file|cerca file|trova file)\s+(.+)', text_clean)
    if find_file_match:
        orig_match = re.search(r'(?:cerca il file|trova il file|cerca file|trova file)\s+(.+)', text, re.IGNORECASE)
        query = orig_match.group(1).strip() if orig_match else find_file_match.group(1).strip()
        return search_local_file(query)

    # ----------------- 8. UTILITIES DI GIOCO (Fase 2) -----------------
    launch_match = re.search(r'(?:avvia|apri lobby)\s+(.+)', text_clean)
    if launch_match:
        orig_match = re.search(r'(?:avvia|apri lobby)\s+(.+)', text, re.IGNORECASE)
        game = orig_match.group(1).strip() if orig_match else launch_match.group(1).strip()
        return launch_game_lobby(game)
        
    server_match = re.search(r'(?:stato server|sono down i server di|stato dei server di)\s+(.+)', text_clean)
    if server_match:
        orig_match = re.search(r'(?:stato server|sono down i server di|stato dei server di)\s+(.+)', text, re.IGNORECASE)
        game = orig_match.group(1).strip() if orig_match else server_match.group(1).strip()
        return check_server_status(game)

    # ----------------- 9. CONTROLLO VOLUME (Fase 1/2) -----------------
    vol_up_match = re.search(r'(?:alza il volume di|alza volume di)\s+(\d+)', text_clean)
    if vol_up_match:
        return adjust_volume(int(vol_up_match.group(1)))
        
    vol_down_match = re.search(r'(?:abbassa il volume di|abbassa volume di)\s+(\d+)', text_clean)
    if vol_down_match:
        return adjust_volume(-int(vol_down_match.group(1)))
        
    vol_set_match = re.search(r'(?:imposta volume a|imposta il volume a|metti il volume a|volume a|volume al)\s+(\d+)', text_clean)
    if vol_set_match:
        return set_volume(int(vol_set_match.group(1)))
        
    if any(k in text_clean for k in ["metti muto", "silenzia volume", "silenzia il volume", "disattiva audio", "muta audio"]):
        return mute_system_volume()

    # ----------------- 10. SPEGNIMENTO / RIAVVIO PC -----------------
    sd_min_match = re.search(r'(?:spegni il pc|spegni il computer|arresta il sistema) tra\s+(\d+)\s+minut', text_clean)
    if sd_min_match:
        minutes = int(sd_min_match.group(1))
        seconds = minutes * 60
        try:
            subprocess.run(["shutdown", "/s", "/t", str(seconds)], creationflags=subprocess.CREATE_NO_WINDOW)
            return True, f"timer_set:{seconds}:Spegnimento PC", ""
        except Exception as e:
            return True, f"Errore nell'impostare il timer: {e}", "Non posso programmare lo spegnimento."

    if any(k in text_clean for k in ["spegni il pc", "spegni il computer", "arresta il sistema"]):
        try:
            subprocess.run(["shutdown", "/s", "/t", "60"], creationflags=subprocess.CREATE_NO_WINDOW)
            return True, "Spegnimento pianificato tra 60 secondi.\nDigita o di' 'annulla spegnimento' per bloccarlo.", "Spegnimento pianificato tra un minuto."
        except Exception:
            return True, "Impossibile spegnere il computer.", "Non posso spegnere il computer."

    if any(k in text_clean for k in ["riavvia il pc", "riavvia il computer", "riavvia il sistema"]):
        try:
            subprocess.run(["shutdown", "/r", "/t", "60"], creationflags=subprocess.CREATE_NO_WINDOW)
            return True, "Riavvio pianificato tra 60 secondi.\nDigita o di' 'annulla spegnimento' per bloccarlo.", "Riavvio pianificato tra un minuto."
        except Exception:
            return True, "Impossibile riavviare il computer.", "Non posso riavviare il computer."

    if any(k in text_clean for k in ["annulla spegnimento", "ferma spegnimento", "annulla arresto", "annulla riavvio"]):
        try:
            subprocess.run(["shutdown", "/a"], creationflags=subprocess.CREATE_NO_WINDOW)
            return True, "Arresto/Riavvio programmato annullato.", "Arresto annullato."
        except Exception:
            return True, "Nessun arresto programmato da annullare.", "Non è stato possibile annullare lo spegnimento."

    # ----------------- 11. SVUOTAMENTO CESTINO -----------------
    if any(k in text_clean for k in ["svuota il cestino", "pulisci il cestino", "svuota cestino"]):
        return empty_recycle_bin()

    # ----------------- 12. PASSWORD GENERATOR -----------------
    pwd_len_match = re.search(r'(?:generami una password|crea password) di\s+(\d+)\s+caratteri', text_clean)
    if pwd_len_match:
        length = int(pwd_len_match.group(1))
        length = max(6, min(64, length))
        password = generate_secure_password(length)
        pyperclip.copy(password)
        return True, f"Password generata: `{password}` (copiata negli appunti).", f"Ho generato una password di {length} caratteri e l'ho copiata negli appunti."

    if any(k in text_clean for k in ["generami una password", "crea una password", "crea password"]):
        password = generate_secure_password(16)
        pyperclip.copy(password)
        return True, f"Password generata: `{password}` (copiata negli appunti).", "Ho generato una password di sedici caratteri e l'ho copiata negli appunti."

    # ----------------- 13. PRENDI APPUNTI AL VOLO -----------------
    note_match = re.search(r'^(?:prendi nota:|prendi nota che|scrivi negli appunti che|scrivi negli appunti:)\s*(.+)', text, re.IGNORECASE)
    if note_match:
        note_content = note_match.group(1).strip()
        try:
            note_file = BASE_DIR / "note_assistente.txt"
            timestamp = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            with open(note_file, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] - {note_content}\n")
            return True, f"Nota registrata in 'note_assistente.txt':\n\"{note_content}\"", "Ho preso nota."
        except Exception as e:
            return True, f"Errore nel salvare la nota: {e}", "Non sono riuscito a salvare la nota."

    # ----------------- 14. CONTROLLO SPOTIFY -----------------
    spotify_match1 = re.search(r'(?:riproduci|metti|cerca|ascolta)\s+(.+?)\s+su\s+spotify', text_clean)
    spotify_match2 = re.search(r'(?:riproduci|metti|cerca|ascolta)\s+su\s+spotify\s+(.+)', text_clean)
    
    spotify_query = None
    if spotify_match1:
        spotify_query = spotify_match1.group(1).strip()
    elif spotify_match2:
        spotify_query = spotify_match2.group(1).strip()
        
    if spotify_query:
        is_api_play, chat_resp, voice_resp = play_track_real_spotify(spotify_query)
        if is_api_play:
            return True, chat_resp, voice_resp
            
        webbrowser.open(f"spotify:search:{spotify_query}")
        def play_first_result():
            try:
                import pyautogui
                time.sleep(2.5)
                pyautogui.press('tab')
                time.sleep(0.2)
                pyautogui.press('enter')
            except Exception:
                pass
        threading.Thread(target=play_first_result, daemon=True).start()
        return True, f"Ricerca ed avvio riproduzione (Fallback) per: '{spotify_query}' su Spotify.", f"Faccio partire {spotify_query} su Spotify."

    # ----------------- 15. CONTROLLO PLAY / PAUSA MULTIMEDIALE -----------------
    play_pause_pattern = r'\b(play|pausa|ferma|riprendi|continua|stop|ripartire)\b.*(musica|canzone|canzoni|audio|video|riproduzione)?'
    if re.search(play_pause_pattern, text_clean) and not ("su spotify" in text_clean or "su youtube" in text_clean or "su yt" in text_clean):
        try:
            import pyautogui
            pyautogui.press('playpause')
            return True, "Eseguito comando di riproduzione/pausa.", "Ho premuto play pausa."
        except Exception:
            return True, "Tasti multimediali non disponibili.", "Tasti multimediali non disponibili."

    smtc_pattern = r'\b(cosa sto ascoltando|prossima canzone|canzone precedente|traccia successiva|canzone successiva)\b'
    if re.search(smtc_pattern, text_clean):
        try:
            import pyautogui
            if "prossima" in text_clean or "successiva" in text_clean:
                pyautogui.press('nexttrack')
                return True, "Passaggio alla prossima traccia eseguito.", "Passo alla prossima canzone."
            elif "precedente" in text_clean:
                pyautogui.press('prevtrack')
                return True, "Passaggio alla traccia precedente eseguito.", "Torno alla canzone precedente."
            else:
                # Per "cosa sto ascoltando", emettiamo un trigger per main.pyw e context_monitor
                return True, "smtc_info_trigger:", ""
        except Exception:
            return True, "Controllo tracce multimediali non disponibile.", "Impossibile controllare la traccia."

    # ----------------- 16. YOUTUBE / YT -----------------
    youtube_match1 = re.search(r'(?:cerca|trova|riproduci|metti)\s+(.+?)\s+su\s+(?:youtube|yt)', text_clean)
    youtube_match2 = re.search(r'(?:cerca|trova|riproduci|metti)\s+su\s+(?:youtube|yt)\s+(.+)', text_clean)
    
    youtube_query = None
    if youtube_match1:
        youtube_query = youtube_match1.group(1).strip()
    elif youtube_match2:
        youtube_query = youtube_match2.group(1).strip()
        
    if youtube_query:
        url = f"https://www.youtube.com/results?search_query={youtube_query.replace(' ', '+')}"
        webbrowser.open(url)
        return True, f"Apertura ricerca YouTube per: '{youtube_query}'", f"Cerco {youtube_query} su YouTube."

    # ----------------- 17. RICERCA GOOGLE -----------------
    web_match1 = re.search(r'(?:cerca|trova|ricerca)\s+(.+?)\s+su\s+(?:google|web|internet)', text_clean)
    web_match2 = re.search(r'(?:cerca|trova|ricerca)\s+su\s+(?:google|web|internet)\s+(.+)', text_clean)
    
    web_query = None
    if web_match1:
        web_query = web_match1.group(1).strip()
    elif web_match2:
        web_query = web_match2.group(1).strip()
        
    if web_query:
        url = f"https://www.google.com/search?q={web_query.replace(' ', '+')}"
        webbrowser.open(url)
        return True, f"Apertura ricerca Google per: '{web_query}'", f"Cerco {web_query} su Google."

    # ----------------- 18. DATA E ORA -----------------
    time_pattern = r'\b(che ore sono|che ora è|dimmi l\'ora|ora attuale)\b'
    if re.search(time_pattern, text_clean):
        now = datetime.datetime.now()
        time_str = now.strftime("%H:%M")
        return True, f"Ora corrente: {time_str}", f"Sono le {time_str}."

    date_pattern = r'\b(che giorno è|data di oggi|che data è oggi|qual è la data)\b'
    if re.search(date_pattern, text_clean):
        now = datetime.datetime.now()
        mesi = [
            "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
            "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"
        ]
        giorni_settimana = [
            "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"
        ]
        giorno_sett = giorni_settimana[now.weekday()]
        mese_str = mesi[now.month - 1]
        date_str = f"{giorno_sett} {now.day} {mese_str} {now.year}"
        return True, f"Data di oggi: {date_str}", f"Oggi è {giorno_sett} {now.day} {mese_str}."

    # ----------------- 19. APERTURA SITI / APP (PIÙ GENERICA, DEVE ESSERE IN FONDO) -----------------
    if any(k == text_clean for k in ["apri il browser", "apri browser", "apri internet", "apri chrome"]):
        webbrowser.open("https://www.google.com")
        return True, "Apertura del browser predefinito.", "Apro il browser."

    apri_match = re.search(r'^apri\s+(.+)', text_clean)
    if apri_match:
        site_or_app = apri_match.group(1).strip()
        if apri_app_locale(site_or_app):
            return True, f"Apertura dell'applicazione locale: '{site_or_app}'", f"Apro {site_or_app}."
            
        sites_map = {
            "google": "https://www.google.com",
            "youtube": "https://www.youtube.com",
            "whatsapp": "https://web.whatsapp.com",
            "facebook": "https://www.facebook.com",
            "instagram": "https://www.instagram.com",
            "gmail": "https://mail.google.com",
            "github": "https://github.com",
            "wikipedia": "https://www.wikipedia.org",
            "spotify": "https://open.spotify.com"
        }
        
        if site_or_app in sites_map:
            url = sites_map[site_or_app]
            webbrowser.open(url)
            return True, f"Apertura del sito web: '{site_or_app}' ({url})", f"Apro {site_or_app}."
            
        return False, "ask_search_confirm", site_or_app

    return False, "", ""

parse_and_execute_command = parse_local_command
