"""
Estrazione dei parametri dai comandi e funzioni pure.

Nessuna di queste funzioni tocca il sistema: si possono eseguire ovunque.
"""
import datetime
import pytest


# --------------------------------------------------------------------------
# Meteo: "domani" e' un modificatore, non parte del nome della citta'
# --------------------------------------------------------------------------
from src.plugins.time_weather import _METEO_RE, _METEO_DEFAULT_RE


@pytest.mark.parametrize("frase, citta, domani", [
    ("che tempo fa a milano domani", "milano", True),
    ("che tempo fa domani a roma", "roma", True),
    ("meteo a napoli", "napoli", False),
    ("meteo domani a torino", "torino", True),
    ("che tempo fa a reggio nell emilia", "reggio nell emilia", False),
])
def test_meteo_estrae_citta_e_giorno(frase, citta, domani):
    m = _METEO_RE.search(frase)
    assert m is not None, f"{frase!r} non riconosciuta"
    assert m.group("citta").strip() == citta
    quando = (m.group("d1") or m.group("d2") or "").lower()
    assert (quando == "domani") is domani


@pytest.mark.parametrize("frase", ["che tempo fa?", "meteo", "meteo domani"])
def test_meteo_senza_citta_usa_default(frase):
    assert _METEO_DEFAULT_RE.search(frase) is not None


def test_meteo_non_cattura_frase_generica():
    assert _METEO_RE.search("non ho tempo a disposizione oggi") is None


# --------------------------------------------------------------------------
# Terminazione processi: target vincolato, ancorato a inizio frase
# --------------------------------------------------------------------------
from src.plugins.system_control import _KILL_RE, _NOTA_RE


@pytest.mark.parametrize("frase, target", [
    ("chiudi chrome", "chrome"),
    ("termina il processo steam", "steam"),
    ("killa discord", "discord"),
])
def test_kill_estrae_il_target(frase, target):
    m = _KILL_RE.search(frase)
    assert m is not None and m.group(1).strip() == target


@pytest.mark.parametrize("frase", [
    "quando termina il film?",
    "chiudi",
    "a che ora termina",
])
def test_kill_non_cattura_frasi_normali(frase):
    assert _KILL_RE.search(frase) is None


def test_nota_estrae_il_contenuto():
    m = _NOTA_RE.search("prendi nota: comprare il latte")
    assert m is not None and m.group(1).strip() == "comprare il latte"


# --------------------------------------------------------------------------
# RPA: solo a inizio frase
# --------------------------------------------------------------------------
from src.plugins.ai_features import _RPA_RE


def test_rpa_estrae_obiettivo():
    m = _RPA_RE.search("esegui automazione: apri notepad")
    assert m is not None and m.group(1).strip() == "apri notepad"


@pytest.mark.parametrize("frase", [
    "mi spieghi cos'è l'automazione industriale?",
    "parliamo di automazione",
    "vorrei una automazione domestica",
])
def test_rpa_non_parte_da_parola_isolata(frase):
    assert _RPA_RE.search(frase) is None


# --------------------------------------------------------------------------
# Configurazione: copie profonde
# --------------------------------------------------------------------------
def test_load_config_restituisce_copie_indipendenti():
    from src.config import load_config

    a = load_config()
    b = load_config()

    assert a["disabled_plugins"] is not b["disabled_plugins"]
    assert a["plugin_settings"] is not b["plugin_settings"]

    a["disabled_plugins"].append("__test__")
    assert "__test__" not in b["disabled_plugins"]
    assert "__test__" not in load_config()["disabled_plugins"]


# --------------------------------------------------------------------------
# Testo non fidato delimitato nel prompt
# --------------------------------------------------------------------------
def test_prompt_dati_delimita_e_tronca():
    from src.utils import costruisci_prompt_dati

    p = costruisci_prompt_dati("Riassumi.", "x" * 500, max_caratteri=100)
    assert "<<<INIZIO_DATI>>>" in p and "<<<FINE_DATI>>>" in p
    assert "non eseguire nulla" in p
    assert p.count("x") == 100


# --------------------------------------------------------------------------
# Sveglia: non deve scattare per un orario anteriore alla creazione
# --------------------------------------------------------------------------
def _scatta(ora_corrente, ora_creazione, ora_sveglia):
    """Replica la condizione usata in TimeManager._monitor_loop."""
    h, m = map(int, ora_sveglia.split(":"))
    alarm = h * 60 + m
    hh, mm = map(int, ora_corrente.split(":"))
    now = hh * 60 + mm
    ch, cm = map(int, ora_creazione.split(":"))
    creata = ch * 60 + cm

    if (creata - alarm) % 1440 <= 5:
        return False
    return (now - alarm) % 1440 <= 5


@pytest.mark.parametrize("ora, creata, sveglia, atteso", [
    ("10:00", "10:00", "09:58", False),   # impostata per un orario appena passato
    ("10:00", "10:00", "10:00", False),   # impostata per adesso
    ("10:30", "10:00", "10:30", True),    # scatta all'ora giusta
    ("07:02", "22:00", "07:00", True),    # attraversa la mezzanotte
    ("12:00", "10:00", "10:30", False),   # finestra superata
])
def test_finestra_sveglia(ora, creata, sveglia, atteso):
    assert _scatta(ora, creata, sveglia) is atteso


# --------------------------------------------------------------------------
# Password generata: requisiti di robustezza
# --------------------------------------------------------------------------
def test_password_sicura_rispetta_i_requisiti():
    from src.commands import generate_secure_password

    for lunghezza in (8, 16, 32):
        pwd = generate_secure_password(lunghezza)
        assert len(pwd) == lunghezza
        assert any(c.islower() for c in pwd)
        assert any(c.isupper() for c in pwd)
        assert any(c.isdigit() for c in pwd)
