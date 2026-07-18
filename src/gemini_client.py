import logging
import os
from pathlib import Path
from PIL import ImageGrab
import google.generativeai as genai
from src.config import load_config

logger = logging.getLogger("OmniMindGemini")

class GeminiClient:
    """
    Gestisce l'integrazione con l'API Google Gemini (modello gemini-2.5-flash).
    Mantiene la cronologia della conversazione, analizza sentiment/immagini/documenti,
    e applica le istruzioni di sistema per plasmare la personalità di OmniMind.
    """
    def __init__(self):
        config = load_config()
        self.api_key = config.get("gemini_api_key", "")
        self.model = None
        self.chat = None
        self.system_instruction = (
            "Sei OmniMind, un assistente virtuale desktop intelligente, ironico e conciso. "
            "Rispondi sempre in italiano. Le tue risposte devono essere brevi, naturali e "
            "facilmente leggibili da un lettore vocale (evita codici lunghi, tabelle complesse, "
            "formattazioni markdown pesanti o risposte verbose, a meno che non sia l'utente a richiederlo espressamente). "
            "Usa un tono brillante, amichevole e ogni tanto scherzoso."
        )
        self._model_name = "gemini-2.5-flash"
        self._initialize()

    def _initialize(self):
        """Inizializza la configurazione dell'SDK Gemini."""
        if not self.api_key:
            logger.warning("GEMINI_API_KEY non trovata nelle variabili d'ambiente. Le API non funzioneranno.")
            return

        try:
            # Configura il client Gemini utilizzando l'API key caricata
            genai.configure(api_key=self.api_key)
            # Carica il modello dall'impostazione di configurazione
            config = load_config()
            self._model_name = config.get("gemini_model", "gemini-2.5-flash")
            self.model = genai.GenerativeModel(
                model_name=self._model_name,
                system_instruction=self.system_instruction
            )
            self.chat = self.model.start_chat(history=[])
            logger.info(f"Client Gemini ({self._model_name}) inizializzato correttamente.")
        except Exception as e:
            logger.error(f"Errore nell'inizializzazione del modello Gemini: {e}")

    def detect_sentiment(self, text: str) -> str:
        """Rileva se l'utente mostra segni di rabbia, frustrazione o frenesia (es. uso del maiuscolo o parole forti)."""
        is_angry = False
        
        # Rileva se scrive in maiuscolo (frenesia)
        if text.isupper() and len(text) > 5:
            is_angry = True
            
        # Rileva parole chiave associate a irritazione o frustrazione
        angry_keywords = ["rabbia", "cazzo", "merda", "fanculo", "odio", "uffa", "non funziona", "schifo", "rompe", "stupido"]
        text_lower = text.lower()
        if any(w in text_lower for w in angry_keywords):
            is_angry = True
            
        if is_angry:
            logger.info("Rilevato tono di frustrazione/rabbia. OmniMind adotterà risposte calme ed empatiche.")
            return (
                "[ISTRUZIONE DI SISTEMA TEMPORANEA: L'utente sembra frustrato, arrabbiato o agitato. "
                "Rispondi con un tono calmo, empatico, rassicurante e pacato. Sii cordiale e supportalo per rasserenarlo.]\n"
            )
        return ""

    def send_message(self, message_text: str) -> tuple[str, str | None]:
        """Invia un messaggio all'interno della chat logica di Gemini, richiedendo sia testo che audio."""
        if not self.api_key:
            return (
                "Ciao! Non posso ancora connettermi al mio cervello. "
                "Per favore, imposta la tua chiave GEMINI_API_KEY nelle impostazioni e riavviami.",
                None
            )
            
        try:
            # Rileva il profilo attivo e adatta le istruzioni di sistema a runtime
            config = load_config()
            active_profile = config.get("active_profile", "Nessuno")
            sys_inst = self.system_instruction
            
            if active_profile == "Gaming":
                sys_inst += (
                    "\n[ATTENZIONE: Rispondi in modalità sintetica ed essenziale. Massima brevità (massimo 10-15 parole), "
                    "in modo telegrafico e schematico. L'utente sta giocando, non dilungarti per nessun motivo.]"
                )
            elif active_profile == "Notte":
                sys_inst += (
                    "\n[ATTENZIONE: Rispondi con un tono rilassante, pacato ed empatico, ideale per la notte.]"
                )
                
            self.model = genai.GenerativeModel(
                model_name=self._model_name,
                system_instruction=sys_inst
            )
            # Trasferisci la cronologia della chat precedente al nuovo modello
            old_history = self.chat.history if self.chat else []
            self.chat = self.model.start_chat(history=old_history)
        except Exception as e:
            logger.error(f"Errore nel configurare il modello dinamico: {e}")

        if not self.chat:
            return "C'è stato un problema nella configurazione del modulo AI.", None

        try:
            # Analisi del tono/sentiment ed inserimento di prompt euristico invisibile
            sentiment_directive = self.detect_sentiment(message_text)
            full_prompt = f"{sentiment_directive}{message_text}"
            
            # Invia il prompt testuale
            response = self.chat.send_message(full_prompt)
            
            text_response = ""
            audio_bytes = None
            
            try:
                if response.candidates and response.candidates[0].content.parts:
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, "text") and part.text:
                            text_response += part.text
                        elif hasattr(part, "inline_data") and part.inline_data:
                            mime = getattr(part.inline_data, "mime_type", "")
                            if "audio" in mime:
                                audio_bytes = getattr(part.inline_data, "data", None)
            except Exception as ex:
                logger.error(f"Errore durante l'estrazione delle parti di Gemini: {ex}")

            # Se la risposta audio non contiene testo trascritto, proviamo a richiederlo
            if not text_response.strip():
                logger.warning("Nessun testo trascritto nella risposta di Gemini. Provo a richiederlo...")
                try:
                    text_model = genai.GenerativeModel(model_name=self._model_name, system_instruction=sys_inst)
                    text_resp = text_model.generate_content(message_text)
                    text_response = text_resp.text
                except Exception as ex:
                    logger.error(f"Errore nel recupero testo: {ex}")
                    text_response = "Ecco la mia risposta audio."
            
            audio_path = None
            if audio_bytes:
                from src.config import TEMP_DIR
                audio_path = os.path.join(TEMP_DIR, "gemini_speech.mp3")
                with open(audio_path, "wb") as f:
                    f.write(audio_bytes)
                    
            return text_response, audio_path
        except Exception as e:
            logger.error(f"Errore durante l'invio del messaggio a Gemini: {e}")
            return "Scusa, c'è un problema di connessione con i server di Gemini. Verifica la connessione internet o la tua chiave API.", None

    def analyze_screenshot(self, user_prompt: str) -> tuple[str, str | None]:
        """Cattura lo schermo del PC ed esegue un'analisi visiva dello screenshot tramite Gemini."""
        if not self.api_key or not self.model:
            return "Modulo AI non configurato. Impossibile analizzare lo schermo.", None
            
        try:
            from src.config import TEMP_DIR
            logger.info("Cattura dello screenshot in corso per visione multimodale...")
            screenshot = ImageGrab.grab(all_screens=True)
            capture_path = os.path.join(TEMP_DIR, "vision_capture.png")
            screenshot.save(capture_path)
            
            system_prompt = (
                "Sei l'assistente desktop dell'utente. Analizza questo screenshot dello schermo del computer, "
                "identifica se ci sono errori di codice, bug, messaggi di errore o spiega cosa stai vedendo in modo conciso, "
                "diretto e informale in lingua italiana."
            )
            full_prompt = f"{system_prompt}\nRichiesta utente: {user_prompt}"
            
            # Passa l'immagine PIL direttamente all'SDK multimodale
            response = self.model.generate_content([screenshot, full_prompt])
            response_text = response.text if response.text else "Non sono riuscito ad analizzare lo screenshot."
            return response_text, capture_path
        except Exception as e:
            logger.error(f"Errore durante la visione dello schermo: {e}")
            return f"Errore durante la cattura o analisi visiva dello schermo: {e}", None

    def summarize_document(self, file_path: str) -> str:
        """Legge un file .txt o .pdf ed invia il testo a Gemini per estrarre un riassunto strutturato."""
        if not self.api_key or not self.model:
            return "Modulo AI non configurato. Impossibile analizzare il documento."
            
        path = Path(file_path.strip('"\' '))
        if not path.exists():
            return f"Errore: il file localizzato in `{file_path}` non esiste sul disco."
            
        suffix = path.suffix.lower()
        text_content = ""
        
        try:
            if suffix == ".txt":
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    text_content = f.read()
            elif suffix == ".pdf":
                from pypdf import PdfReader
                reader = PdfReader(path)
                pages = []
                # Limita la lettura alle prime 20 pagine per non saturare la memoria
                max_pages = min(20, len(reader.pages))
                for i in range(max_pages):
                    page_text = reader.pages[i].extract_text()
                    if page_text:
                        pages.append(page_text)
                text_content = "\n".join(pages)
            else:
                return f"Errore: estensione '{suffix}' non supportata. OmniMind analizza solo file .txt e .pdf."
                
            if not text_content.strip():
                return "Il file caricato sembra essere vuoto o privo di testo decifrabile."
                
            # Limita i caratteri da inviare per sicurezza
            snippet = text_content[:55000]
            
            prompt = (
                "Sei un riassuntore esperto. Leggi il seguente documento ed estrai un riassunto strutturato in punti chiave "
                "molto chiari e ordinati in italiano. Suddividi in argomenti principali.\n\n"
                f"--- INIZIO DOCUMENTO ---\n{snippet}\n--- FINE DOCUMENTO ---"
            )
            
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Errore nel riassumere il documento: {e}")
            return f"Si è verificato un errore durante l'estrazione del testo: {e}"

    def gaming_expert_advice(self, query: str) -> str:
        """Restituisce consigli su gaming/build agendo come un eSports coach professionista."""
        if not self.api_key or not self.model:
            return "Modulo AI non configurato. Impossibile chiedere consigli di gaming."
            
        prompt = (
            "Sei un eSports Coach professionista di videogiochi competitivi. Fornisci consigli su build, rune, "
            "oggetti, strategie, tattiche o counter-picks per il gioco o personaggio indicato. "
            "Rispondi in italiano in modo estremamente sintetico, schematico e diretto, usando termini tipici dei gamer "
            "per non interrompere il flusso di gioco dell'utente.\n"
            f"Domanda dell'utente: {query}"
        )
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Errore nel modulo coaching AI: {e}")
            return "Non ho potuto contattare il tuo coach eSports di fiducia al momento."

    def translate_phrase(self, phrase: str, target_language: str) -> str:
        """Richiede una traduzione esatta e pulita della frase nella lingua specificata."""
        if not self.api_key or not self.model:
            return "Modulo AI non configurato. Traduzione non disponibile."
            
        prompt = (
            f"Traduci la seguente frase in {target_language}. "
            "Fornisci come risposta unicamente la frase tradotta finale. Evita qualsiasi commento, "
            "spiegazione, introduzione o l'uso di virgolette.\n"
            f"Frase da tradurre: {phrase}"
        )
        try:
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Errore traduzione: {e}")
            return f"Errore durante la traduzione in {target_language}."

    def build_rpa_sequence(self, user_prompt: str) -> str:
        """Scompone l'obiettivo dell'utente in un array JSON di azioni RPA per Windows."""
        if not self.api_key:
            return "[]"
            
        system_instruction = (
            "Sei un Motore RPA Autonomo e Intelligente. L'utente ti fornirà un OBIETTIVO AD ALTO LIVELLO (es. 'apri il blocco note e scrivimi una poesia' oppure 'cerca i risultati della serie A su youtube'). "
            "Il tuo compito è INFERIRE tutti i passaggi fisici intermedi necessari senza che l'utente debba dettarteli. "
            "REGOLA 1: Inserisci SEMPRE un'azione 'sleep' di 2 o 3 secondi dopo aver aperto un programma o caricato un sito web, per dare tempo all'interfaccia di apparire prima di scrivere.\n"
            "REGOLA 2: Non limitarti a tradurre. Se l'utente ti chiede di 'scrivere una barzelletta' o 'fare un esempio', INVENTA TU il testo direttamente nell'azione 'type_text'.\n"
            "REGOLA 3: Ricorda di premere 'enter' dopo aver digitato url o cercato nella barra di start.\n"
            "Azioni consentite:\n"
            "- 'open_app': {'action': 'open_app', 'target': 'URL oppure nome eseguibile'}\n"
            "- 'type_text': {'action': 'type_text', 'target': 'testo da digitare'}\n"
            "- 'press_key': {'action': 'press_key', 'target': 'nome_tasto' (enter, tab, win, esc)}\n"
            "- 'hotkey': {'action': 'hotkey', 'target': 'tasti separati da virgola' (es. ctrl,c o win,r)}\n"
            "- 'sleep': {'action': 'sleep', 'target': 'numero di secondi'}\n"
            "Esempio 'apri notepad e scrivi un haiku': [{ 'action': 'hotkey', 'target': 'win,r' }, { 'action': 'type_text', 'target': 'notepad' }, { 'action': 'press_key', 'target': 'enter' }, { 'action': 'sleep', 'target': '2' }, { 'action': 'type_text', 'target': 'Foglie d autunno\\ncadono lievi al suolo\\nvento d inverno.' }]\n"
            "Rispondi SOLO con l'array JSON valido e nulla più."
        )
        
        try:
            rpa_model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                system_instruction=system_instruction,
                generation_config={"response_mime_type": "application/json"}
            )
            response = rpa_model.generate_content(user_prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Errore durante la generazione della sequenza RPA: {e}")
            return "[]"

    def analyze_system(self, sys_data: dict, user_prompt: str) -> str:
        if not self.api_key: return "Modulo AI non configurato."
        import json
        sys_info = json.dumps(sys_data, indent=2)
        
        system_prompt = (
            "Sei OmniMind, un Sistemista IT esperto. Ricevi i dati hardware del PC in JSON (CPU, RAM, GPU, e i Top Processi). "
            "Sintetizza in modo discorsivo (2-3 frasi) la salute del sistema. "
            "REGOLA GAMING: Se noti tra i processi aperti nomi legati a videogiochi (es. Roblox, Steam, ecc), "
            "è PERFETTAMENTE NORMALE che la GPU sia sotto forte sforzo (anche 100%). NON generare allarmi per l'uso percentuale "
            "della GPU. Genera un allarme SOLO SE la temperatura della GPU ('gpu_temp_c') supera gli 80°C o se un programma non-game satura RAM anomala."
        )
        full_prompt = f"La richiesta dell'utente era: '{user_prompt}'. Hardware: {sys_info}"
        
        try:
            response = self.model.generate_content([system_prompt, full_prompt])
            return response.text.replace("*", "")
        except Exception as e:
            return f"Errore diagnostica hardware: {e}"

    def reset_chat(self):
        """Reinizializza la chat per svuotare la cronologia."""
        if self.model:
            self.chat = self.model.start_chat(history=[])
            logger.info("Cronologia della chat di OmniMind resettata.")
