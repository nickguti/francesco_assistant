import re
import logging
from src.plugins.base_plugin import OmniMindPlugin
from src import safety

logger = logging.getLogger("PluginAIFeatures")

# Ancorato a inizio frase: la parola "automazione" isolata dentro una domanda
# innescava l'esecuzione di macro reali su tastiera e mouse.
_RPA_RE = re.compile(r'^(?:esegui\s+automazion[ei]|fai questo per me)\b\s*:?\s*(.+)', re.IGNORECASE)

class AIFeaturesPlugin(OmniMindPlugin):
    """
    Gestisce i trigger per le funzionalità di intelligenza artificiale avanzata:
    RPA, Analisi Schermo, Lettura Appunti, Riassunto Documenti e Traduzione.
    Restituiscono trigger asincroni a main.pyw.
    """
    name = "Intelligenza Artificiale"
    description = "Gestisce l'automazione RPA, la traduzione linguistica, la visione dello schermo e il riassunto di documenti locali."
    priority = 40
    examples = [
        ("esegui automazione: apri il blocco note e scrivi una poesia", "Sequenza di azioni su tastiera e finestre"),
        ("analizza lo schermo", "Cattura lo schermo e lo fa analizzare"),
        ("spiegami gli appunti", "Legge e analizza il contenuto degli appunti"),
        ("riassumi il documento C:/percorso/file.pdf", "Riassunto di un file .txt o .pdf"),
        ("traduci in inglese: buongiorno", "Traduzione istantanea"),
    ]

    def can_handle(self, text_clean: str, text: str) -> bool:
        if _RPA_RE.search(text): return True
        if any(k in text_clean for k in ["guarda qui", "spiegami cosa c'è a schermo", "analizza questo errore", "guarda lo schermo", "analizza lo schermo"]): return True
        if any(k in text_clean for k in ["analizza appunti", "spiegami gli appunti", "spiegami gli appunti di windows", "analizza gli appunti", "analizza il clipboard", "spiega appunti"]): return True
        if re.search(r'\b(?:riassumi il documento|leggi questo file|riassumi il file|leggi il file)\s+(.+)', text_clean): return True
        if re.search(r'traduci in\s+([a-zA-Z\s]+?):\s*(.+)', text, re.IGNORECASE): return True
        if re.search(r'come si dice\s+(.+?)\s+in\s+([a-zA-Z\s]+)', text, re.IGNORECASE): return True
        return False

    def execute(self, text_clean: str, text: str) -> tuple[bool, str, str]:
        rpa_match = _RPA_RE.search(text)
        if rpa_match:
            prompt = rpa_match.group(1).strip()
            # L'automazione muove tastiera e mouse reali su una sequenza
            # inventata dal modello: e' l'azione piu' invasiva dell'app.
            if safety.serve_conferma():
                return safety.richiedi(
                    f"Sto per eseguire un'automazione su tastiera e finestre per: **{prompt}**. Confermi?",
                    "Confermi l'esecuzione dell'automazione?")
            return True, f"rpa_trigger:{prompt}", ""
            
        if any(k in text_clean for k in ["guarda qui", "spiegami cosa c'è a schermo", "analizza questo errore", "guarda lo schermo", "analizza lo schermo"]):
            prompt = text.strip()
            return True, f"vision_trigger:{prompt}", ""
            
        if any(k in text_clean for k in ["analizza appunti", "spiegami gli appunti", "spiegami gli appunti di windows", "analizza gli appunti", "analizza il clipboard", "spiega appunti"]):
            return True, "clipboard_analyze_trigger:", ""
            
        doc_match = re.search(r'\b(?:riassumi il documento|leggi questo file|riassumi il file|leggi il file)\s+(.+)', text_clean)
        if doc_match:
            orig_match = re.search(r'\b(?:riassumi il documento|leggi questo file|riassumi il file|leggi il file)\s+(.+)', text, re.IGNORECASE)
            path = orig_match.group(1).strip() if orig_match else doc_match.group(1).strip()
            return True, f"doc_summary_trigger:{path}", ""
            
        trans_match1 = re.search(r'traduci in\s+([a-zA-Z\s]+?):\s*(.+)', text, re.IGNORECASE)
        if trans_match1:
            lang = trans_match1.group(1).strip()
            phrase = trans_match1.group(2).strip()
            return True, f"translate_trigger:{lang}:{phrase}", ""
            
        trans_match2 = re.search(r'come si dice\s+(.+?)\s+in\s+([a-zA-Z\s]+)', text, re.IGNORECASE)
        if trans_match2:
            phrase = trans_match2.group(1).strip()
            lang = trans_match2.group(2).strip()
            return True, f"translate_trigger:{lang}:{phrase}", ""
            
        return False, "", ""
