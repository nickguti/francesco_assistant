import os
import re
import webbrowser
import logging
from src.plugins.base_plugin import OmniMindPlugin
from src.commands import apri_app_locale

logger = logging.getLogger("PluginAppsLauncher")

class AppsLauncherPlugin(OmniMindPlugin):
    name = "Lanciatore di App e Web"
    description = "Avvia programmi locali istantaneamente ed esegue ricerche su Google e YouTube."
    # Ultimo in ordine di dispatch: "apri <qualsiasi cosa>" e' un catch-all e
    # non deve precedere i plugin con trigger specifici.
    priority = 90
    examples = [
        ("apri blocco note", "Avvia un'applicazione di sistema"),
        ("cerca ricette veloci su google", "Ricerca sul web"),
        ("metti lo-fi su youtube", "Ricerca su YouTube"),
    ]

    """
    Gestisce l'avvio rapido di applicazioni di sistema, siti web e ricerche locali di eseguibili.
    """
    def __init__(self):
        self.fast_apps = {
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

    def can_handle(self, text_clean: str, text: str) -> bool:
        for trigger in self.fast_apps.keys():
            if trigger in text_clean:
                return True
                
        if any(k == text_clean for k in ["apri il browser", "apri browser", "apri internet", "apri chrome"]):
            return True
            
        if re.search(r'(?:cerca|trova|riproduci|metti)\s+(.+?)\s+su\s+(?:youtube|yt)', text_clean) or re.search(r'(?:cerca|trova|riproduci|metti)\s+su\s+(?:youtube|yt)\s+(.+)', text_clean):
            return True
            
        if re.search(r'(?:cerca|trova|ricerca)\s+(.+?)\s+su\s+(?:google|web|internet)', text_clean) or re.search(r'(?:cerca|trova|ricerca)\s+su\s+(?:google|web|internet)\s+(.+)', text_clean):
            return True
            
        # Esclude le forme piu' specifiche gestite da altri plugin
        # (es. "apri lobby valorant" appartiene al plugin Gaming).
        if re.search(r'^apri\s+(?!lobby\b)(.+)', text_clean):
            return True
            
        return False

    def execute(self, text_clean: str, text: str) -> tuple[bool, str, str]:
        # Fast Apps
        for trigger, target in self.fast_apps.items():
            if trigger in text_clean:
                if target.startswith("http") or target.endswith(":"):
                    webbrowser.open(target)
                else:
                    os.system(f"start {target}")
                return True, f"Apertura istantanea di {trigger.replace('apri ', '')}... 🚀", "Fatto."
                
        # Browser generico
        if any(k == text_clean for k in ["apri il browser", "apri browser", "apri internet", "apri chrome"]):
            webbrowser.open("https://www.google.com")
            return True, "Apertura del browser predefinito.", "Apro il browser."

        # Web Search
        youtube_match1 = re.search(r'(?:cerca|trova|riproduci|metti)\s+(.+?)\s+su\s+(?:youtube|yt)', text_clean)
        youtube_match2 = re.search(r'(?:cerca|trova|riproduci|metti)\s+su\s+(?:youtube|yt)\s+(.+)', text_clean)
        youtube_query = None
        if youtube_match1: youtube_query = youtube_match1.group(1).strip()
        elif youtube_match2: youtube_query = youtube_match2.group(1).strip()
        if youtube_query:
            url = f"https://www.youtube.com/results?search_query={youtube_query.replace(' ', '+')}"
            webbrowser.open(url)
            return True, f"Apertura ricerca YouTube per: '{youtube_query}'", f"Cerco {youtube_query} su YouTube."
            
        web_match1 = re.search(r'(?:cerca|trova|ricerca)\s+(.+?)\s+su\s+(?:google|web|internet)', text_clean)
        web_match2 = re.search(r'(?:cerca|trova|ricerca)\s+su\s+(?:google|web|internet)\s+(.+)', text_clean)
        web_query = None
        if web_match1: web_query = web_match1.group(1).strip()
        elif web_match2: web_query = web_match2.group(1).strip()
        if web_query:
            url = f"https://www.google.com/search?q={web_query.replace(' ', '+')}"
            webbrowser.open(url)
            return True, f"Apertura ricerca Google per: '{web_query}'", f"Cerco {web_query} su Google."

        # App o Sito generico
        apri_match = re.search(r'^apri\s+(?!lobby\b)(.+)', text_clean)
        if apri_match:
            site_or_app = apri_match.group(1).strip()
            # Tenta prima con l'app locale
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
