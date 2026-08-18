"""
Conferma delle azioni irreversibili.

L'impostazione `safe_mode_confirm` esisteva gia' nella GUI e nel config, ma
nessun modulo la leggeva: era un interruttore che prometteva una protezione
inesistente. Qui viene resa effettiva riusando la macchina a stati di conferma
gia' presente in main.pyw per la ricerca su Google.

Flusso: il plugin che sta per eseguire un'azione distruttiva chiama
`serve_conferma()`. Se ritorna True, restituisce `richiedi(...)` invece di
agire; main.pyw memorizza la richiesta originale e la ripete dentro
`conferma_concessa()` solo dopo un si' esplicito dell'utente.
"""
import threading
from src.config import get_setting

# Il flag e' per-thread: viene impostato nello stesso thread che ri-esegue il
# comando dopo la conferma, quindi non puo' essere ereditato per sbaglio da
# un'altra richiesta in corso.
_local = threading.local()

PREFISSO = "confirm_required:"


def serve_conferma() -> bool:
    """True se l'azione va confermata e la conferma non e' gia' stata data."""
    if getattr(_local, "concessa", False):
        return False
    return bool(get_setting("safe_mode_confirm", False))


def richiedi(domanda: str, domanda_voce: str = "") -> tuple[bool, str, str]:
    """Risposta standard di un plugin che sospende un'azione in attesa di conferma."""
    return True, f"{PREFISSO}{domanda}", (domanda_voce or domanda)


class conferma_concessa:
    """Context manager: dentro il blocco, `serve_conferma()` ritorna False."""

    def __enter__(self):
        _local.concessa = True
        return self

    def __exit__(self, *exc):
        _local.concessa = False
        return False
