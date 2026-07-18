import logging
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QAction
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu

logger = logging.getLogger("OmniMindTray")

class TrayIconManager:
    """
    Gestisce l'icona nella system tray usando PyQt6 nativo (QSystemTrayIcon).
    Non necessita di un thread separato in quanto gira nel Main Event Loop di Qt.
    """
    def __init__(self, on_show_callback, on_toggle_mute_callback, on_exit_callback, get_mute_status_callback):
        self.on_show = on_show_callback
        self.on_toggle_mute = on_toggle_mute_callback
        self.on_exit = on_exit_callback
        self.get_mute_status = get_mute_status_callback
        self.tray_icon = None

    def _create_icon(self) -> QIcon:
        """Genera un'immagine icona elegante nativamente con QPainter."""
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Sfondo cerchio blu scuro semitrasparente con bordo celeste neon
        painter.setBrush(QColor(26, 36, 43, 220))
        pen = QPen(QColor(0, 206, 209, 255))
        pen.setWidth(3)
        painter.setPen(pen)
        painter.drawEllipse(4, 4, 56, 56)
        
        # Disegna una 'O' stilizzata (un cerchio interno neon spesso)
        painter.setBrush(Qt.GlobalColor.transparent)
        pen.setWidth(5)
        painter.setPen(pen)
        painter.drawEllipse(18, 18, 28, 28)
        
        painter.end()
        return QIcon(pixmap)

    def set_icon_by_state(self, state: str):
        import os
        from PyQt6.QtGui import QIcon, QPixmap
        from PyQt6.QtCore import Qt
        
        # Mappatura corretta: listening = attesa wake word (idle)
        icon_map = {
            "listening": "azzurra.png", 
            "recording": "rossa.png",
            "processing": "gialla.png", 
            "gemini_thinking": "gialla.png",
            "speaking": "verde.png", 
            "muted": "viola.png",
            "idle": "azzurra.png", 
            "downloading": "gialla.png"
        }
        
        assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
        filename = icon_map.get(state, "azzurra.png")
        icon_path = os.path.join(assets_dir, filename)
        
        if os.path.exists(icon_path):
            # Carica come Pixmap per gestire meglio le risoluzioni
            pixmap = QPixmap(icon_path)
            self.tray_icon.setIcon(QIcon(pixmap))
        else:
            self.tray_icon.setIcon(self._create_icon())

    def _update_mute_text(self):
        """Aggiorna il testo dell'azione mute nel menu."""
        if self.get_mute_status():
            self.mute_action.setText("🎤 Attiva Ascolto Vocale")
        else:
            self.mute_action.setText("🔇 Disattiva Ascolto Vocale")

    def toggle_mute_wrapper(self):
        # Esegue la callback
        self.on_toggle_mute()
        # Aggiorna subito il testo dell'azione del menu
        self._update_mute_text()

    def start(self):
        """Avvia l'icona della barra di sistema all'interno dell'Event Loop Qt."""
        self.tray_icon = QSystemTrayIcon()
        self.tray_icon.setIcon(self._create_icon())
        self.tray_icon.setToolTip("OmniMind - Assistente Virtuale")
        
        # Gestisce il doppio click sull'icona per aprire la GUI
        self.tray_icon.activated.connect(self._on_tray_activated)
        
        # Creazione del menu contestuale
        self.menu = QMenu()
        
        # Stile base per il menu contestuale per matchare la dark mode
        self.menu.setStyleSheet("""
            QMenu {
                background-color: #1e293b;
                color: #f1f5f9;
                border: 1px solid #334155;
            }
            QMenu::item {
                padding: 5px 20px 5px 20px;
            }
            QMenu::item:selected {
                background-color: #38bdf8;
                color: #0f172a;
            }
        """)
        
        self.show_action = QAction("🖥️ Apri OmniMind", self.menu)
        self.show_action.triggered.connect(self.on_show)
        # Rendiamo 'Apri OmniMind' l'azione di default (bold)
        font = self.show_action.font()
        font.setBold(True)
        self.show_action.setFont(font)
        
        self.mute_action = QAction("", self.menu)
        self._update_mute_text()
        self.mute_action.triggered.connect(self.toggle_mute_wrapper)
        
        self.exit_action = QAction("❌ Esci", self.menu)
        self.exit_action.triggered.connect(self.on_exit)
        
        self.menu.addAction(self.show_action)
        self.menu.addAction(self.mute_action)
        self.menu.addSeparator()
        self.menu.addAction(self.exit_action)
        
        self.tray_icon.setContextMenu(self.menu)
        self.tray_icon.show()
        logger.info("Icona System Tray caricata nativamente tramite QSystemTrayIcon.")

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.on_show()

    def stop(self):
        """Rimuove l'icona dalla tray bar."""
        if self.tray_icon:
            self.tray_icon.hide()
            logger.info("Icona System Tray arrestata.")
