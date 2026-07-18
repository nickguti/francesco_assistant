import re
import logging
from src.plugins.base_plugin import OmniMindPlugin
from src.commands import launch_game_lobby, check_server_status, trigger_discord_call

logger = logging.getLogger("PluginGaming")

class GamingPlugin(OmniMindPlugin):
    """
    Gestisce avvio giochi, controllo server, discord, e il consulente eSports.
    """
    def can_handle(self, text_clean: str, text: str) -> bool:
        if re.search(r'(?:avvia|apri lobby)\s+(.+)', text_clean): return True
        if re.search(r'(?:stato server|sono down i server di|stato dei server di)\s+(.+)', text_clean): return True
        if re.search(r'\b(?:consigliami una build per|come countero|build per|consigli per)\s+(.+)', text_clean): return True
        if any(k in text_clean for k in ["entra in chiamata", "entra su discord", "avvia la call", "connettiti al canale vocale"]): return True
        return False

    def execute(self, text_clean: str, text: str) -> tuple[bool, str, str]:
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
            
        gaming_advice_match = re.search(r'\b(?:consigliami una build per|come countero|build per|consigli per)\s+(.+)', text_clean)
        if gaming_advice_match:
            orig_match = re.search(r'\b(?:consigliami una build per|come countero|build per|consigli per)\s+(.+)', text, re.IGNORECASE)
            query = orig_match.group(0).strip() if orig_match else text
            return True, f"gaming_expert_trigger:{query}", ""
            
        if any(k in text_clean for k in ["entra in chiamata", "entra su discord", "avvia la call", "connettiti al canale vocale"]):
            return trigger_discord_call()
            
        return False, "", ""
