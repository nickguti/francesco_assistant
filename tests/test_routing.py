"""
Routing dei comandi verso i plugin.

Questi test interrogano SOLO `can_handle()`: non chiamano mai `execute()`, che
spegnerebbe il PC, chiuderebbe processi o aprirebbe Steam per davvero.

Coprono i difetti che avevano fatto fare all'assistente il contrario di quanto
chiesto: regex non ancorate e ordine di dispatch dipendente dal nome dei file.
"""
import pytest

from src.plugins.plugin_manager import PluginManager


@pytest.fixture(scope="module")
def plugin_ordinati():
    """
    Tutti i plugin installati, nell'ordine reale di interrogazione.

    Si usa `all_plugins` e non `plugins` per non dipendere da quali plugin
    l'utente ha disabilitato nel proprio config.json.
    """
    pm = PluginManager()
    return sorted(pm.all_plugins.values(), key=lambda p: (p.priority, p.__class__.__name__))


def chi_gestisce(plugin_ordinati, frase):
    """Nome del primo plugin che dichiara di saper gestire la frase, o None."""
    pulita = frase.lower().strip()
    for plugin in plugin_ordinati:
        if plugin.can_handle(pulita, frase):
            return plugin.__class__.__name__
    return None


# --------------------------------------------------------------------------
# Comandi che devono raggiungere il plugin giusto
# --------------------------------------------------------------------------
@pytest.mark.parametrize("frase, atteso", [
    # Il bug piu' grave: "attiva" veniva trovato dentro "dis-attiva", quindi
    # la disattivazione era irraggiungibile e il profilo veniva ATTIVATO.
    ("attiva modalità gaming", "SystemControlPlugin"),
    ("disattiva modalità gaming", "SystemControlPlugin"),
    ("disattiva profilo notte", "SystemControlPlugin"),

    # "avvia" veniva trovato dentro "riavvia": il riavvio finiva al plugin Gaming.
    ("riavvia il pc", "SystemControlPlugin"),
    ("spegni il pc", "SystemControlPlugin"),

    # Dentro il plugin Gaming, il lanciatore precedeva i trigger Discord.
    ("avvia la call", "GamingPlugin"),
    ("entra su discord", "GamingPlugin"),
    ("avvia valorant", "GamingPlugin"),

    # Il catch-all "^apri" di AppsLauncher rubava le forme piu' specifiche.
    ("apri lobby valorant", "GamingPlugin"),
    ("apri blocco note", "AppsLauncherPlugin"),
    ("cerca ricette veloci su google", "AppsLauncherPlugin"),

    # Il ramo esisteva in execute() ma non aveva trigger in can_handle().
    ("prendi nota: comprare il latte", "SystemControlPlugin"),
    ("scrivi negli appunti che domani piove", "SystemControlPlugin"),

    ("chiudi chrome", "SystemControlPlugin"),
    ("che ore sono", "TimeWeatherPlugin"),
    ("timer di 10 minuti", "TimeWeatherPlugin"),
    ("sveglia alle 07:30", "TimeWeatherPlugin"),
    ("metti in pausa", "MultimediaPlugin"),
    ("esegui automazione: apri il blocco note", "AIFeaturesPlugin"),
    ("analizza lo schermo", "AIFeaturesPlugin"),
])
def test_comando_va_al_plugin_giusto(plugin_ordinati, frase, atteso):
    assert chi_gestisce(plugin_ordinati, frase) == atteso


# --------------------------------------------------------------------------
# Frasi normali che NON devono attivare alcun comando
# --------------------------------------------------------------------------
@pytest.mark.parametrize("frase", [
    # "termina" nuda dirottava sulla terminazione dei processi.
    "quando termina il film?",
    # "automazione" nuda faceva partire macro reali su tastiera e mouse.
    "mi spieghi cos'è l'automazione industriale?",
    "parliamo un attimo di automazione",
    # "prestazioni" nuda avviava la diagnostica hardware.
    "come posso migliorare le prestazioni di photoshop?",
    # "consigli per" nudo finiva al coach eSports.
    "dammi consigli per studiare meglio",
    # "tempo a" nudo veniva letto come richiesta meteo.
    "non ho tempo a disposizione oggi",
    # Conversazione ordinaria
    "ciao come stai",
    "raccontami una barzelletta",
])
def test_frase_normale_non_intercettata(plugin_ordinati, frase):
    gestore = chi_gestisce(plugin_ordinati, frase)
    assert gestore is None, f"{frase!r} intercettata da {gestore}"


# --------------------------------------------------------------------------
# Priorita' esplicita: rinominare un file non deve cambiare il comportamento
# --------------------------------------------------------------------------
def test_apps_launcher_e_ultimo(plugin_ordinati):
    """Il catch-all "apri <qualsiasi cosa>" deve essere interrogato per ultimo."""
    assert plugin_ordinati[-1].__class__.__name__ == "AppsLauncherPlugin"


def test_priorita_tutte_distinte(plugin_ordinati):
    priorita = [p.priority for p in plugin_ordinati]
    assert len(priorita) == len(set(priorita)), f"priorita' duplicate: {priorita}"


def test_ogni_plugin_dichiara_esempi(plugin_ordinati):
    """Gli esempi alimentano la guida comandi nella GUI."""
    for plugin in plugin_ordinati:
        assert getattr(plugin, "examples", None), f"{plugin.__class__.__name__} non dichiara esempi"
