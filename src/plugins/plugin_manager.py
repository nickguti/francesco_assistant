import importlib
import logging
import sys
from pathlib import Path
from src.plugins.base_plugin import OmniMindPlugin
from src.config import get_setting

logger = logging.getLogger("OmniMindPluginManager")

# Moduli della cartella plugins che non contengono plugin caricabili.
_SKIP_FILES = ("base_plugin.py", "plugin_manager.py")


class PluginManager:
    def __init__(self):
        self.all_plugins = {}  # {stem: istanza}
        self.plugins = []      # istanze attive, ordinate per priority
        self.load_plugins()

    def load_plugins(self, reload_modules: bool = False):
        """
        Carica (o ricarica) i plugin dalla cartella plugins.
        Azzera sempre lo stato precedente: senza questo, ogni ricarica
        accodava istanze duplicate alla lista di dispatch.
        """
        self.all_plugins = {}
        self.plugins = []

        plugins_dir = Path(__file__).parent
        disabled_plugins = get_setting("disabled_plugins", [])

        for file in sorted(plugins_dir.glob("*.py")):
            if file.name.startswith("_") or file.name in _SKIP_FILES:
                continue

            module_name = f"src.plugins.{file.stem}"
            try:
                module = importlib.import_module(module_name)
                if reload_modules and module_name in sys.modules:
                    module = importlib.reload(module)

                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type)
                            and issubclass(attr, OmniMindPlugin)
                            and attr is not OmniMindPlugin
                            and attr.__module__ == module_name):
                        instance = attr()
                        self.all_plugins[file.stem] = instance

                        if file.stem in disabled_plugins:
                            logger.info(f"Plugin {file.stem} caricato in memoria ma disabilitato per il dispatch.")
                        else:
                            self.plugins.append(instance)
                            logger.debug(f"Plugin attivato: {attr.__name__} (priority={attr.priority})")
            except Exception as e:
                logger.error(f"Errore nel caricamento del plugin {module_name}: {e}")

        # L'ordine di interrogazione e' una decisione dichiarata, non l'ordine
        # alfabetico dei nomi file: rinominare un file non deve cambiare
        # il comportamento dell'assistente.
        self.plugins.sort(key=lambda p: (p.priority, p.__class__.__name__))

        ordine = ", ".join(f"{p.__class__.__name__}({p.priority})" for p in self.plugins)
        logger.info(f"Totale plugin attivi: {len(self.plugins)} — ordine: {ordine}")

    def dispatch(self, text: str) -> tuple[bool, str, str]:
        text_clean = text.lower().strip()
        for plugin in self.plugins:
            try:
                if not plugin.can_handle(text_clean, text):
                    continue

                result = plugin.execute(text_clean, text)
                is_command, chat_response, _voice = result

                # Un can_handle piu' permissivo di execute non deve far morire
                # il comando: se il plugin non ha prodotto nulla, si prosegue
                # con i plugin successivi invece di restituire subito.
                if not is_command and not chat_response:
                    logger.debug(
                        f"{plugin.__class__.__name__} ha dichiarato il comando ma non lo ha gestito; proseguo."
                    )
                    continue

                logger.info(f"Comando gestito dal plugin: {plugin.__class__.__name__}")
                return result
            except Exception as e:
                logger.error(f"Errore durante l'esecuzione del plugin {plugin.__class__.__name__}: {e}")

        # Nessun plugin ha gestito il comando
        return False, "", ""
