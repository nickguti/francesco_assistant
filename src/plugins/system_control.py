import re
import ctypes
import subprocess
import logging
from src.plugins.base_plugin import OmniMindPlugin
from src.commands import (
    empty_recycle_bin, get_system_resources_status, 
    get_ip_addresses, check_port_status, organize_downloads, 
    extract_latest_download, search_local_file, adjust_volume, 
    set_volume, mute_system_volume, disattiva_profili, attiva_profilo,
    generate_secure_password
)
import pyperclip
from src import safety

logger = logging.getLogger("PluginSystemControl")

# Ancorato a inizio frase e con target vincolato: le parole nude "chiudi" e
# "termina" seguite da (.+) dirottavano frasi normali ("quando termina il
# film?") sulla terminazione forzata dei processi.
_KILL_RE = re.compile(
    r"^(?:chiudi(?: il programma)?|termina(?: il processo| l'app)?|killa|killami|forza chiusura)\s+([\w .\-]{2,40})$",
    re.IGNORECASE,
)
# Il ramo "prendi nota" era implementato in execute() ma non aveva alcun
# trigger in can_handle(), quindi non era raggiungibile da nessun input.
_NOTA_RE = re.compile(
    r"^(?:prendi nota[:\s]|prendi nota che\s|scrivi negli appunti[:\s])\s*(.+)",
    re.IGNORECASE,
)

class SystemControlPlugin(OmniMindPlugin):
    """
    Gestisce controlli di sistema, hardware, rete, file e alimentazione.
    """
    name = "Controllo Sistema"
    description = "Gestisce azioni core come blocco/spegnimento PC, profili audio e luminosità, e monitoraggio delle risorse hardware."
    priority = 50
    examples = [
        ("blocca il pc", "Blocca la sessione di Windows"),
        ("stato hardware", "Diagnostica di CPU, RAM e GPU"),
        ("imposta il volume a 30", "Regola il volume master"),
        ("attiva profilo gaming", "Applica un profilo di sistema"),
        ("chiudi chrome", "Termina i processi di un programma"),
        ("prendi nota: comprare il latte", "Salva una nota su file"),
    ]

    def can_handle(self, text_clean: str, text: str) -> bool:
        triggers = [
            "blocca il pc", "blocca il computer", "chiudi a chiave",
            "mostra il desktop", "abbassa le finestre", "nascondi tutto",
            "svuota il cestino", "butta l'immondizia", "pulisci il cestino", "svuota cestino",
            "come sta il pc", "analisi di sistema", "status pc", "stato del sistema",
            "prestazioni del pc", "prestazioni del sistema", "prestazioni hardware",
            "ripristina profilo standard", "ripristina standard", "ripristina modalità standard",
            "quanta ram sto usando", "stato cpu", "temperatura hardware", "risorse di sistema", "stato hardware", "consumo risorse",
            "qual è il mio ip", "mio ip", "ip pubblico", "ip locale",
            "fai ordine nei download", "organizza i download", "pulisci la cartella download", "organizza download",
            "estrai l'ultimo download", "scompatta l'ultimo download", "scompatta ultimo file", "estrai ultimo file",
            "metti muto", "silenzia volume", "silenzia il volume", "disattiva audio", "muta audio",
            "spegni il pc", "spegni il computer", "arresta il sistema",
            "riavvia il pc", "riavvia il computer", "riavvia il sistema",
            "annulla spegnimento", "ferma spegnimento", "annulla arresto", "annulla riavvio",
            "generami una password", "crea una password", "crea password"
        ]
        
        if any(k in text_clean for k in triggers):
            return True
            
        if _KILL_RE.search(text_clean): return True
        if _NOTA_RE.search(text.strip()): return True
        if re.search(r'\b(?:attiva|abilita)\s+(?:modalità|profilo)\s+(gaming|gioco|focus|studio|notte|relax)', text_clean): return True
        if re.search(r'(?:disattiva|disabilita)\s+(?:modalità|profilo|profili)\s*(gaming|gioco|focus|studio|notte|relax)?', text_clean): return True
        if re.search(r'(?:controlla porta|verifica porta|controlla la porta|verifica la porta)\s+(\d+)', text_clean): return True
        if re.search(r'(?:cerca il file|trova il file|cerca file|trova file)\s+(.+)', text_clean): return True
        if re.search(r'(?:alza il volume di|alza volume di)\s+(\d+)', text_clean): return True
        if re.search(r'(?:abbassa il volume di|abbassa volume di)\s+(\d+)', text_clean): return True
        if re.search(r'(?:imposta volume a|imposta il volume a|metti il volume a|volume a|volume al)\s+(\d+)', text_clean): return True
        if re.search(r'(?:spegni il pc|spegni il computer|arresta il sistema) tra\s+(\d+)\s+minut', text_clean): return True
        if re.search(r'(?:generami una password|crea password) di\s+(\d+)\s+caratteri', text_clean): return True
        
        return False

    def execute(self, text_clean: str, text: str) -> tuple[bool, str, str]:
        if any(k in text_clean for k in ["blocca il pc", "blocca il computer", "chiudi a chiave"]):
            ctypes.windll.user32.LockWorkStation()
            return True, "Computer bloccato. 🔒", "PC bloccato."
            
        if any(k in text_clean for k in ["mostra il desktop", "abbassa le finestre", "nascondi tutto"]):
            import pyautogui
            pyautogui.hotkey('win', 'd')
            return True, "Desktop mostrato. 🖥️", "Finestre abbassate."
            
        if any(k in text_clean for k in ["svuota il cestino", "butta l'immondizia", "pulisci il cestino", "svuota cestino"]):
            if safety.serve_conferma():
                return safety.richiedi("Sto per svuotare definitivamente il Cestino. Confermi?",
                                       "Confermi lo svuotamento del cestino?")
            return empty_recycle_bin()
            
        if any(k in text_clean for k in ["come sta il pc", "analisi di sistema", "status pc", "stato del sistema",
                                         "prestazioni del pc", "prestazioni del sistema", "prestazioni hardware"]):
            return True, "system_diagnostics_trigger:", ""

        kill_match = _KILL_RE.search(text.strip())
        if kill_match:
            app_name = kill_match.group(1).strip()
            if app_name and app_name.lower() not in ["", "tutto", "omnimind"]:
                if safety.serve_conferma():
                    return safety.richiedi(
                        f"Sto per chiudere forzatamente i processi di **{app_name}**. Confermi?",
                        f"Confermi la chiusura di {app_name}?")
                return True, f"process_kill_trigger:{app_name}", ""
                
        if any(k in text_clean for k in ["ripristina profilo standard", "ripristina standard", "ripristina modalità standard"]):
            return disattiva_profili()
            
        # La disattivazione va valutata PRIMA dell'attivazione. Senza il \b
        # iniziale la regex di attivazione veniva trovata dentro la parola
        # "dis-attiva", quindi "disattiva modalità gaming" finiva per ATTIVARE
        # il profilo Gaming: l'utente otteneva l'opposto di quanto chiesto.
        disable_profile_match = re.search(r'\b(?:disattiva|disabilita)\s+(?:modalità|profilo|profili)\s*(gaming|gioco|focus|studio|notte|relax)?', text_clean)
        if disable_profile_match:
            return disattiva_profili()

        active_profile_match = re.search(r'\b(?:attiva|abilita)\s+(?:modalità|profilo)\s+(gaming|gioco|focus|studio|notte|relax)', text_clean)
        if active_profile_match:
            prof = active_profile_match.group(1)
            if prof in ["gaming", "gioco"]: return attiva_profilo("gaming")
            elif prof in ["focus", "studio"]: return attiva_profilo("focus")
            elif prof in ["notte", "relax"]: return attiva_profilo("notte")
            
        if any(k in text_clean for k in ["quanta ram sto usando", "stato cpu", "temperatura hardware", "risorse di sistema", "stato hardware", "consumo risorse"]):
            return get_system_resources_status()
            
        if any(k in text_clean for k in ["qual è il mio ip", "mio ip", "ip pubblico", "ip locale"]):
            return get_ip_addresses()
            
        port_match = re.search(r'(?:controlla porta|verifica porta|controlla la porta|verifica la porta)\s+(\d+)', text_clean)
        if port_match:
            return check_port_status(int(port_match.group(1)))
            
        if any(k in text_clean for k in ["fai ordine nei download", "organizza i download", "pulisci la cartella download", "organizza download"]):
            if safety.serve_conferma():
                return safety.richiedi("Sto per spostare i file della cartella Download in sottocartelle. Confermi?",
                                       "Confermi il riordino dei download?")
            return organize_downloads()
            
        if any(k in text_clean for k in ["estrai l'ultimo download", "scompatta l'ultimo download", "scompatta ultimo file", "estrai ultimo file"]):
            return extract_latest_download()
            
        find_file_match = re.search(r'(?:cerca il file|trova il file|cerca file|trova file)\s+(.+)', text_clean)
        if find_file_match:
            orig_match = re.search(r'(?:cerca il file|trova il file|cerca file|trova file)\s+(.+)', text, re.IGNORECASE)
            query = orig_match.group(1).strip() if orig_match else find_file_match.group(1).strip()
            return search_local_file(query)
            
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
            
        sd_min_match = re.search(r'(?:spegni il pc|spegni il computer|arresta il sistema) tra\s+(\d+)\s+minut', text_clean)
        if sd_min_match:
            minutes = int(sd_min_match.group(1))
            seconds = minutes * 60
            if safety.serve_conferma():
                return safety.richiedi(f"Sto per programmare lo spegnimento del PC tra {minutes} minuti. Confermi?",
                                       f"Confermi lo spegnimento tra {minutes} minuti?")
            try:
                subprocess.run(["shutdown", "/s", "/t", str(seconds)], creationflags=subprocess.CREATE_NO_WINDOW)
                return True, f"timer_set:{seconds}:Spegnimento PC", ""
            except Exception as e:
                return True, f"Errore nell'impostare il timer: {e}", "Non posso programmare lo spegnimento."

        if any(k in text_clean for k in ["spegni il pc", "spegni il computer", "arresta il sistema"]):
            if safety.serve_conferma():
                return safety.richiedi("Sto per spegnere il PC tra 60 secondi. Confermi?",
                                       "Confermi lo spegnimento del computer?")
            try:
                subprocess.run(["shutdown", "/s", "/t", "60"], creationflags=subprocess.CREATE_NO_WINDOW)
                return True, "Spegnimento pianificato tra 60 secondi.\nDigita o di' 'annulla spegnimento' per bloccarlo.", "Spegnimento pianificato tra un minuto."
            except Exception:
                return True, "Impossibile spegnere il computer.", "Non posso spegnere il computer."

        if any(k in text_clean for k in ["riavvia il pc", "riavvia il computer", "riavvia il sistema"]):
            if safety.serve_conferma():
                return safety.richiedi("Sto per riavviare il PC tra 60 secondi. Confermi?",
                                       "Confermi il riavvio del computer?")
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

        pwd_len_match = re.search(r'(?:generami una password|crea password) di\s+(\d+)\s+caratteri', text_clean)
        if pwd_len_match:
            length = int(pwd_len_match.group(1))
            length = max(6, min(64, length))
            password = generate_secure_password(length)
            pyperclip.copy(password)
            # Il valore non viene restituito in chat: ogni chat_response di un
            # comando sincrono viene persistito in chiaro in chat_history.
            return True, f"Password di {length} caratteri generata e copiata negli appunti. Non la mostro e non la salvo nella cronologia.", f"Ho generato una password di {length} caratteri e l'ho copiata negli appunti."

        if any(k in text_clean for k in ["generami una password", "crea una password", "crea password"]):
            password = generate_secure_password(16)
            pyperclip.copy(password)
            return True, "Password di 16 caratteri generata e copiata negli appunti. Non la mostro e non la salvo nella cronologia.", "Ho generato una password di sedici caratteri e l'ho copiata negli appunti."

        note_match = _NOTA_RE.search(text.strip())
        if note_match:
            import datetime
            from src.config import BASE_DIR
            note_content = note_match.group(1).strip()
            try:
                note_file = BASE_DIR / "note_assistente.txt"
                timestamp = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                with open(note_file, "a", encoding="utf-8") as f:
                    f.write(f"[{timestamp}] - {note_content}\n")
                return True, f"Nota registrata in 'note_assistente.txt':\n\"{note_content}\"", "Ho preso nota."
            except Exception as e:
                return True, f"Errore nel salvare la nota: {e}", "Non sono riuscito a salvare la nota."

        return False, "", ""
