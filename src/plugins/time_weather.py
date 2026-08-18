import re
import datetime
import logging
from src.plugins.base_plugin import OmniMindPlugin
from src.commands import (
    check_weather, get_tech_news,
    add_todo_task, get_todo_list_text, remove_todo_task
)

logger = logging.getLogger("PluginTimeWeather")

# "domani" e' un modificatore, non parte del nome della citta': con il
# vecchio (.+) greedy, "che tempo fa a milano domani" cercava la localita'
# "milano domani", e "che tempo fa domani a roma" non veniva riconosciuto.
_METEO_RE = re.compile(
    r"^(?:che tempo fa|che tempo far[aà]|meteo|previsioni)\s*(?P<d1>domani|oggi)?\s*(?:a|ad|in|su)\s+"
    r"(?P<citta>[^,?!.]+?)\s*(?P<d2>domani|oggi)?\s*[?.!]*$",
    re.IGNORECASE,
)
_METEO_DEFAULT_RE = re.compile(r'^(?:che tempo fa|meteo|previsioni)\s*(domani|oggi)?\s*[?.!]*$', re.IGNORECASE)

class TimeWeatherPlugin(OmniMindPlugin):
    """
    Gestisce ora, data, timer, sveglie, meteo, notizie e la to-do list.
    """
    name = "Produttività e Utilità"
    description = "Offre le funzionalità di orologio, meteo, timer, sveglie, e gestione to-do list."
    # Trigger molto specifici (timer, sveglia, meteo, to-do): interrogato per primo.
    priority = 10
    examples = [
        ("che ore sono", "Ora corrente"),
        ("timer di 10 minuti per la pasta", "Avvia un timer con allarme"),
        ("sveglia alle 07:30", "Imposta una sveglia"),
        ("che tempo fa domani a Roma", "Meteo di oggi o domani"),
        ("aggiungi comprare il pane alla lista", "Aggiunge una voce alla to-do list"),
        ("notizie tech", "Ultime notizie tecnologiche"),
    ]

    def get_settings_schema(self):
        return [
            {"key": "citta_meteo", "label": "Città predefinita per il meteo", "type": "str", "default": "Milano"},
            {"key": "usa_formato_24h", "label": "Usa formato orario a 24 ore", "type": "bool", "default": True}
        ]

    def can_handle(self, text_clean: str, text: str) -> bool:
        if re.search(r'\b(che ore sono|che ora è|dimmi l\'ora|ora attuale)\b', text_clean): return True
        if re.search(r'\b(che giorno è|data di oggi|che data è oggi|qual è la data)\b', text_clean): return True
        
        if re.search(r'\btimer\b\s+(?:di|da|per)?\s*(\d+)\s*(second|minut|or)\w*(?:\s+(?:per|chiamato|di)\s+(.+))?', text_clean): return True
        if re.search(r'\bsveglia\b\s+(?:alle|per le)?\s*(\d{1,2})[:.](\d{2})(?:\s+(?:per|chiamata|di)\s+(.+))?', text_clean): return True
        
        if re.search(r'aggiungi\s+(.+?)\s+a(?:l|lle|lla)?\s+(?:cose da fare|to-do list|lista)', text_clean): return True
        if any(k in text_clean for k in ["mostra la mia lista", "mostra la to-do list", "mostra cose da fare", "cosa ho da fare", "mostra la lista"]): return True
        if re.search(r'(?:rimuovi|cancella|elimina)\s+(.+?)\s+da(?:lla|lle)?\s+(?:to-do list|cose da fare|lista)', text_clean): return True
        
        if _METEO_RE.search(text_clean) or _METEO_DEFAULT_RE.search(text_clean): return True
        if any(k in text_clean for k in ["quali sono le ultime notizie tech", "dimmi le notizie del giorno", "notizie del giorno", "tecnologia notizie", "notizie tech", "ultime notizie"]): return True
        
        return False

    def execute(self, text_clean: str, text: str) -> tuple[bool, str, str]:
        if re.search(r'\b(che ore sono|che ora è|dimmi l\'ora|ora attuale)\b', text_clean):
            now = datetime.datetime.now()
            # Rispetta l'impostazione del plugin, finora dichiarata ma mai letta.
            usa_24h = self.get_settings().get("usa_formato_24h", True)
            time_str = now.strftime("%H:%M") if usa_24h else now.strftime("%I:%M %p")
            return True, f"Ora corrente: {time_str}", f"Sono le {time_str}."
            
        if re.search(r'\b(che giorno è|data di oggi|che data è oggi|qual è la data)\b', text_clean):
            now = datetime.datetime.now()
            mesi = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
            giorni_settimana = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
            giorno_sett = giorni_settimana[now.weekday()]
            mese_str = mesi[now.month - 1]
            date_str = f"{giorno_sett} {now.day} {mese_str} {now.year}"
            return True, f"Data di oggi: {date_str}", f"Oggi è {giorno_sett} {now.day} {mese_str}."

        timer_match = re.search(r'\btimer\b\s+(?:di|da|per)?\s*(\d+)\s*(second|minut|or)\w*(?:\s+(?:per|chiamato|di)\s+(.+))?', text_clean)
        if timer_match:
            val = int(timer_match.group(1))
            unit = timer_match.group(2)
            label = timer_match.group(3).strip() if timer_match.group(3) else "Timer"
            seconds = val
            if "minut" in unit: seconds = val * 60
            elif "or" in unit: seconds = val * 3600
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
            
        weather_match = _METEO_RE.search(text.strip())
        if weather_match:
            city = weather_match.group('citta').strip()
            quando = weather_match.group('d1') or weather_match.group('d2') or ''
            return check_weather(city, quando.lower() == 'domani')

        # "che tempo fa" senza citta': usa quella configurata nel plugin.
        default_match = _METEO_DEFAULT_RE.search(text.strip())
        if default_match:
            citta = (self.get_settings().get('citta_meteo') or 'Milano').strip()
            quando = default_match.group(1) or ''
            return check_weather(citta, quando.lower() == 'domani')
            
        if any(k in text_clean for k in ["quali sono le ultime notizie tech", "dimmi le notizie del giorno", "notizie del giorno", "tecnologia notizie", "notizie tech", "ultime notizie"]):
            return get_tech_news()

        return False, "", ""
