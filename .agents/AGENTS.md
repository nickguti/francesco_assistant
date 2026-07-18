# Prompt Formatting Guidelines per le Chat Deleate (Subagents)

Quando viene richiesto di generare un prompt da fornire ad altre chat (es. Chat Core & Routing, Chat GUI & Tray, Chat Gemini & AI), il prompt deve **rigorosamente** rispettare la seguente struttura. Il tono deve essere tecnico e diretto. Ogni sezione deve essere presente; se non applicabile, esplicitare il motivo.

### 1. Contesto della modifica
Spiegare cosa fa attualmente il codice coinvolto, perché non è sufficiente e qual è l'obiettivo della modifica. Non dare nulla per scontato.

### 2. Localizzazione precisa
Indicare il file esatto, nome della funzione/metodo, numero di riga approssimativo se disponibile, e il blocco di codice originale da cercare.

### 3. La modifica
Fornire il codice nuovo completo e pronto all'uso, con commenti inline che spiegano le scelte non ovvie. Se la modifica tocca più punti del file, elencarli tutti nell'ordine in cui vanno applicati.

### 4. Motivazione tecnica
Spiegare perché questa soluzione e non un'alternativa. Esplicitare eventuali trade-off (performance, leggibilità, accoppiamento tra moduli).

### 5. Effetti collaterali e rischi
Analizzare cosa potrebbe rompersi in altri moduli, quali edge case vanno tenuti d'occhio, o se la modifica richiede aggiornamenti in altri file (e quali).

### 6. Checklist di verifica finale
Fornire una lista di controlli concreti e specifici che l'AI ricevente deve eseguire dopo aver applicato la modifica per confermare che tutto funzioni (cosa testare, con quale input, quale output attendersi, cosa non deve accadere). Evitare generici "verifica che funzioni".
