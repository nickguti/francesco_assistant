import re
import logging
from src.plugins.base_plugin import OmniMindPlugin
from src.commands import launch_game_lobby, check_server_status, trigger_discord_call

logger = logging.getLogger("PluginGaming")

# Tutti i pattern sono ancorati a inizio frase: senza ancoraggio "avvia"
# veniva trovato dentro "riavvia il pc" e il comando di riavvio del sistema
# non veniva mai raggiunto.
_LAUNCH_RE = re.compile(r'^(?:avvia|apri lobby)\b\s+(.+)', re.IGNORECASE)
_SERVER_RE = re.compile(r'^(?:stato server|sono down i server di|stato dei server di)\s+(.+)', re.IGNORECASE)
_ADVICE_RE = re.compile(r'^(?:consigliami una build per|come countero|build per|consigli per)\s+(.+)', re.IGNORECASE)

_DISCORD_TRIGGERS = ["entra in chiamata", "entra su discord", "avvia la call", "connettiti al canale vocale"]


class GamingPlugin(OmniMindPlugin):
    """
    Gestisce avvio giochi, controllo server, discord, e il consulente eSports.
    """
    name = "Gaming & eSports"
    description = "Lancia le lobby di gioco, monitora lo stato dei server ed offre consigli in gioco stile eSports Coach."
    priority = 30
    examples = [
        ("avvia valorant", "Lancia il gioco tramite il protocollo del launcher"),
        ("apri lobby cs2", "Apre la lobby di un gioco Steam"),
        ("stato server di riot games", "Verifica se i server sono raggiungibili"),
        ("entra in chiamata", "Macro di ingresso nel canale vocale Discord"),
        ("consigliami una build per jinx", "Consiglio in stile coach eSports"),
    ]

    def can_handle(self, text_clean: str, text: str) -> bool:
        if any(k in text_clean for k in _DISCORD_TRIGGERS): return True
        if _LAUNCH_RE.search(text_clean): return True
        if _SERVER_RE.search(text_clean): return True
        if _ADVICE_RE.search(text_clean): return True
        return False

    def execute(self, text_clean: str, text: str) -> tuple[bool, str, str]:
        # Discord per primo: "avvia la call" soddisfa anche _LAUNCH_RE, e con
        # l'ordine invertito finiva nel lanciatore di giochi senza mai
        # raggiungere la macro Discord.
        if any(k in text_clean for k in _DISCORD_TRIGGERS):
            return trigger_discord_call()

        launch_match = _LAUNCH_RE.search(text)
        if launch_match:
            return launch_game_lobby(launch_match.group(1).strip())

        server_match = _SERVER_RE.search(text)
        if server_match:
            return check_server_status(server_match.group(1).strip())

        advice_match = _ADVICE_RE.search(text)
        if advice_match:
            # group(1), non group(0): con group(0) la frase-trigger finiva
            # dentro la query inviata al modello.
            return True, f"gaming_expert_trigger:{advice_match.group(1).strip()}", ""

        return False, "", ""
