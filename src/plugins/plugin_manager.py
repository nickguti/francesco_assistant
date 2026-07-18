import importlib
import logging
from pathlib import Path
from src.plugins.base_plugin import OmniMindPlugin

logger = logging.getLogger("OmniMindPluginManager")

class PluginManager:
    def __init__(self):
        self.plugins = []
        self._load_plugins()

    def _load_plugins(self):
        plugins_dir = Path(__file__).parent
        for file in plugins_dir.glob("*.py"):
            if file.name.startswith("_") or file.name in ("base_plugin.py", "plugin_manager.py"):
                continue
            
            module_name = f"src.plugins.{file.stem}"
            try:
                module = importlib.import_module(module_name)
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, type) and issubclass(attr, OmniMindPlugin) and attr is not OmniMindPlugin:
                        self.plugins.append(attr())
                        logger.debug(f"Plugin caricato: {attr.__name__}")
            except Exception as e:
                logger.error(f"Errore nel caricamento del plugin {module_name}: {e}")
        
        logger.info(f"Totale plugin caricati: {len(self.plugins)}")

    def dispatch(self, text: str) -> tuple[bool, str, str]:
        text_clean = text.lower().strip()
        for plugin in self.plugins:
            try:
                if plugin.can_handle(text_clean, text):
                    logger.info(f"Comando intercettato dal plugin: {plugin.__class__.__name__}")
                    return plugin.execute(text_clean, text)
            except Exception as e:
                logger.error(f"Errore durante l'esecuzione del plugin {plugin.__class__.__name__}: {e}")
                
        # Nessun plugin ha gestito il comando
        return False, "", ""
