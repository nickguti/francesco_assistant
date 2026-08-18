import sqlite3
import logging
import threading
from src.config import BASE_DIR

logger = logging.getLogger("OmniMindDatabase")
DB_PATH = BASE_DIR / "omnimind_data.db"

# Lock globale per sincronizzare l'accesso al DB da thread diversi (es. GUI, Voice, Comandi)
# Garantisce robustezza e zero perdita di dati
db_lock = threading.Lock()

def get_connection():
    """Ritorna una connessione al database SQLite ottimizzata."""
    # timeout=10.0 previene "database is locked" in caso di delay
    # check_same_thread=False permette l'uso sicuro tra thread (sincronizzato dal lock)
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0, check_same_thread=False)
    # Abilitiamo WAL (Write-Ahead Logging) per maggiore concorrenza e robustezza su Windows
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    """Inizializza il database creando le tabelle necessarie se non esistono."""
    with db_lock:
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Tabella cronologia chat
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    sender TEXT NOT NULL,
                    message TEXT NOT NULL
                )
            """)

            # Timer e sveglie: vivevano solo in memoria, quindi chiudere
            # l'applicazione cancellava silenziosamente tutto quanto impostato.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS timers (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    deadline TEXT NOT NULL,
                    total INTEGER NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alarms (
                    id TEXT PRIMARY KEY,
                    time_str TEXT NOT NULL,
                    label TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()
            logger.info("Database SQLite inizializzato con successo.")
        except Exception as e:
            logger.error(f"Errore durante l'inizializzazione del database: {e}")
        finally:
            if conn:
                conn.close()

def save_chat_message(sender: str, message: str):
    """Salva un messaggio della chat nel database."""
    with db_lock:
        conn = None
        try:
            conn = get_connection()
            conn.execute(
                "INSERT INTO chat_history (sender, message) VALUES (?, ?)",
                (sender, message)
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Errore nel salvare il messaggio in chat_history: {e}")
        finally:
            if conn:
                conn.close()

MAX_MESSAGGI_STORICI = 5000


def purge_chat_history(mantieni: int = MAX_MESSAGGI_STORICI) -> int:
    """
    Elimina i messaggi piu' vecchi oltre la soglia.
    Senza retention il database cresceva indefinitamente e nessuna funzione
    permetteva all'utente di ridurlo.
    """
    with db_lock:
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM chat_history WHERE id <= "
                "(SELECT MAX(id) FROM chat_history) - ?", (mantieni,))
            rimossi = cur.rowcount or 0
            conn.commit()
            return max(0, rimossi)
        except Exception as e:
            logger.error(f"Errore nella pulizia della cronologia: {e}")
            return 0
        finally:
            if conn:
                conn.close()


def clear_chat_history() -> bool:
    """Svuota completamente la cronologia della chat."""
    with db_lock:
        conn = None
        try:
            conn = get_connection()
            conn.execute("DELETE FROM chat_history")
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Errore nello svuotare la cronologia: {e}")
            return False
        finally:
            if conn:
                conn.close()


def _esegui(sql: str, params: tuple = (), fetch: bool = False):
    """Helper interno per le tabelle di timer e sveglie."""
    with db_lock:
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(sql, params)
            if fetch:
                return cur.fetchall()
            conn.commit()
            return None
        except Exception as e:
            logger.error(f"Errore SQL ({sql.split()[0]}): {e}")
            return [] if fetch else None
        finally:
            if conn:
                conn.close()


def salva_timer(timer_id: str, label: str, deadline_iso: str, total: int):
    _esegui("INSERT OR REPLACE INTO timers (id, label, deadline, total) VALUES (?, ?, ?, ?)",
            (timer_id, label, deadline_iso, total))


def rimuovi_timer(timer_id: str):
    _esegui("DELETE FROM timers WHERE id = ?", (timer_id,))


def leggi_timers() -> list:
    return _esegui("SELECT id, label, deadline, total FROM timers", fetch=True) or []


def salva_sveglia(alarm_id: str, time_str: str, label: str, created_iso: str):
    _esegui("INSERT OR REPLACE INTO alarms (id, time_str, label, created_at) VALUES (?, ?, ?, ?)",
            (alarm_id, time_str, label, created_iso))


def rimuovi_sveglia(alarm_id: str):
    _esegui("DELETE FROM alarms WHERE id = ?", (alarm_id,))


def leggi_sveglie() -> list:
    return _esegui("SELECT id, time_str, label, created_at FROM alarms", fetch=True) or []


def get_last_chat_messages(limit: int = 50) -> list:
    """Ritorna gli ultimi `limit` messaggi memorizzati, in ordine cronologico."""
    with db_lock:
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT sender, message FROM chat_history ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            return list(reversed(rows))
        except Exception as e:
            logger.error(f"Errore nel recupero della cronologia chat: {e}")
            return []
        finally:
            if conn:
                conn.close()
