import threading
import queue
import asyncio
import psutil
import pyperclip
import logging

try:
    from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
except ImportError:
    GlobalSystemMediaTransportControlsSessionManager = None

logger = logging.getLogger("ContextMonitor")

class ContextMonitor(threading.Thread):
    def __init__(self, out_queue, in_queue=None):
        super().__init__(daemon=True)
        self.out_queue = out_queue
        self.in_queue = in_queue or queue.Queue()
        self.loop = None
        self.last_clipboard = ""
        self.running = True
        self.smtc_manager = None
        self.smtc_token = None
        self.night_triggered_today = False
        self.gaming_triggered_now = False

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.main_loop())

    async def main_loop(self):
        # Inizializza SMTC se disponibile
        if GlobalSystemMediaTransportControlsSessionManager:
            try:
                self.smtc_manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
                if self.smtc_manager:
                    self.smtc_token = self.smtc_manager.add_sessions_changed(self.on_sessions_changed)
                    # Trigger iniziale
                    asyncio.create_task(self.update_media_info(self.smtc_manager))
            except Exception as e:
                logger.error(f"Errore inizializzazione SMTC: {e}")
        else:
            logger.warning("winsdk non installato. Controllo media SMTC disabilitato.")

        # Task paralleli
        task_telemetry = asyncio.create_task(self.poll_telemetry())
        task_clipboard = asyncio.create_task(self.poll_clipboard())
        task_commands = asyncio.create_task(self.poll_commands())
        task_triggers = asyncio.create_task(self.poll_triggers())

        await asyncio.gather(task_telemetry, task_clipboard, task_commands, task_triggers)

    async def poll_triggers(self):
        """Polling delle automazioni di sistema e trigger ogni 10 secondi."""
        import time
        from src.config import load_config
        while self.running:
            try:
                config = load_config()
                trigger_time_night = config.get("trigger_time_night", "").strip()
                trigger_app_gaming = config.get("trigger_app_gaming", "").strip().lower()
                active_profile = config.get("active_profile", "Nessuno")
                
                # Controllo Trigger Notte
                if trigger_time_night and len(trigger_time_night) >= 4:
                    current_time = time.strftime("%H:%M")
                    if current_time == trigger_time_night and not self.night_triggered_today:
                        if active_profile != "Notte":
                            self.out_queue.put(("automation_trigger", "Notte"))
                        self.night_triggered_today = True
                    elif current_time != trigger_time_night:
                        # Reset per il giorno successivo
                        self.night_triggered_today = False
                
                # Controllo Trigger Gaming (Processi)
                if trigger_app_gaming:
                    target = trigger_app_gaming if trigger_app_gaming.endswith(".exe") else trigger_app_gaming + ".exe"
                    app_running = False
                    
                    # Scansione processi leggera
                    for proc in psutil.process_iter(['name']):
                        try:
                            if proc.info['name'] and proc.info['name'].lower() == target:
                                app_running = True
                                break
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                            
                    if app_running and not self.gaming_triggered_now:
                        if active_profile != "Gaming":
                            self.out_queue.put(("automation_trigger", "Gaming"))
                        self.gaming_triggered_now = True
                    elif not app_running and self.gaming_triggered_now:
                        self.gaming_triggered_now = False
                        
            except Exception as e:
                logger.error(f"Errore controllo trigger automazioni: {e}")
                
            await asyncio.sleep(10.0)

    async def poll_telemetry(self):
        """Polling delle risorse di sistema ogni 5 secondi."""
        while self.running:
            try:
                cpu = psutil.cpu_percent()
                ram = psutil.virtual_memory()
                ram_avail_gb = ram.available / (1024 ** 3)
                ram_percent = ram.percent
                
                # Invia un evento telemetria
                self.out_queue.put(("system_telemetry", {
                    "cpu_percent": cpu,
                    "ram_percent": ram_percent,
                    "ram_avail_gb": ram_avail_gb
                }))
            except Exception as e:
                logger.error(f"Errore telemetria: {e}")
            await asyncio.sleep(5.0)

    async def poll_clipboard(self):
        """Polling della clipboard ogni 0.5 secondi."""
        # Inizializza l'ultimo valore letto senza triggerare l'evento alla partenza
        try:
            self.last_clipboard = pyperclip.paste()
        except Exception:
            self.last_clipboard = ""

        while self.running:
            try:
                current_clipboard = pyperclip.paste()
                if current_clipboard != self.last_clipboard and current_clipboard.strip():
                    self.last_clipboard = current_clipboard
                    # Invia l'evento clipboard
                    self.out_queue.put(("clipboard_event", current_clipboard))
            except Exception:
                # pyperclip potrebbe lanciare eccezioni se la clipboard è bloccata da altri processi, ignoriamo silenziosamente
                pass
            await asyncio.sleep(0.5)

    async def poll_commands(self):
        """Polling leggero per comandi in ingresso dalla GUI/Core."""
        while self.running:
            try:
                cmd = self.in_queue.get_nowait()
                if isinstance(cmd, tuple) and len(cmd) >= 2:
                    cmd_type, action = cmd[0], cmd[1]
                    if cmd_type == "media_control" and self.smtc_manager:
                        await self.handle_media_command(action)
            except queue.Empty:
                pass
            except Exception as e:
                logger.error(f"Errore gestione comandi ContextMonitor: {e}")
            await asyncio.sleep(0.1)

    async def handle_media_command(self, action):
        session = self.smtc_manager.get_current_session()
        if not session:
            return
        
        try:
            if action == "play_pause":
                info = session.get_playback_info()
                # GlobalSystemMediaTransportControlsSessionPlaybackStatus: 4 = Playing, 5 = Paused
                if info.playback_status == 4:
                    await session.try_pause_async()
                else:
                    await session.try_play_async()
            elif action == "next":
                await session.try_skip_next_async()
            elif action == "prev":
                await session.try_skip_previous_async()
        except Exception as e:
            logger.error(f"Errore esecuzione comando media: {e}")

    def on_sessions_changed(self, sender, args):
        """Gestore eventi di sistema per modifiche alla sessione multimediale (es. nuova canzone o pausa)."""
        if self.loop and self.running:
            # Schedula in modo thread-safe l'aggiornamento nell'event loop asincrono
            asyncio.run_coroutine_threadsafe(self.update_media_info(sender), self.loop)

    async def update_media_info(self, manager):
        session = manager.get_current_session()
        if session:
            try:
                info = await session.try_get_media_properties_async()
                playback_info = session.get_playback_info()
                
                title = info.title if info.title else "Sconosciuto"
                artist = info.artist if info.artist else "Sconosciuto"
                # GlobalSystemMediaTransportControlsSessionPlaybackStatus: 4 = Playing
                status = "Playing" if playback_info.playback_status == 4 else "Paused"
                
                self.out_queue.put(("media_status", {
                    "title": title,
                    "artist": artist,
                    "status": status
                }))
            except Exception as e:
                logger.error(f"Errore recupero info media: {e}")
        else:
            self.out_queue.put(("media_status", None))
