import sqlite3
import logging
import threading
from pathlib import Path
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
            
            # Tabella tracker personale
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS personal_tracker (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome_elemento TEXT NOT NULL,
                    categoria_set TEXT NOT NULL,
                    lingua TEXT NOT NULL,
                    condizione TEXT NOT NULL,
                    completato INTEGER DEFAULT 0
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
