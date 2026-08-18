import logging
import queue
import math
import sys
import os
import subprocess
import time
import winreg
import shutil
import markdown
import psutil
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QPushButton, QTextEdit, QLineEdit, QSlider, QComboBox, QCheckBox,
    QScrollArea, QStackedWidget, QGridLayout, QGroupBox, QFormLayout
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRectF
from PyQt6.QtGui import QColor, QPainter, QTextCursor, QPen

from src.config import load_config, save_config

logger = logging.getLogger("OmniMindGUI")

# Palette attiva, aggiornata da AssistantGUI._apply_theme.
# I colori erano ripetuti come letterali in tutto il file: il tema Chiaro
# calcolava correttamente lo sfondo bianco ma la chat continuava a scrivere
# testo #f8fafc, cioe' bianco su bianco.
TEMA = {
    "bg_main": "#0f172a",
    "card_bg": "#1e293b",
    "card_border": "#1e293b",
    "text_main": "#f8fafc",
    "text_dim": "#94a3b8",
    "accent": "#38bdf8",
    "utente": "#60a5fa",
    "assistente": "#10b981",
}

def interpolate_color(color1_hex, color2_hex, factor):
    c1 = color1_hex.lstrip('#')
    c2 = color2_hex.lstrip('#')
    r1, g1, b1 = int(c1[0:2], 16), int(c1[2:4], 16), int(c1[4:6], 16)
    r2, g2, b2 = int(c2[0:2], 16), int(c2[2:4], 16), int(c2[4:6], 16)
    r = int(r1 + (r2 - r1) * factor)
    g = int(g1 + (g2 - g1) * factor)
    b = int(b1 + (b2 - b1) * factor)
    return QColor(r, g, b)

class StatusCircle(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self.color = QColor("#95a5a6")

    def set_color(self, color):
        if isinstance(color, str):
            color = QColor(color)
        self.color = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.color)
        painter.drawEllipse(2, 2, 12, 12)

class DonutProgressWidget(QWidget):
    def __init__(self, color="#38bdf8", title="CPU"):
        super().__init__()
        self.color = QColor(color)
        self.title = title
        self.value = 0
        self.setMinimumSize(140, 140)

    def setValue(self, val):
        self.value = val
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        size = min(rect.width(), rect.height()) - 20
        x = (rect.width() - size) / 2
        y = (rect.height() - size) / 2
        draw_rect = QRectF(x, y, size, size)

        # Sfondo del cerchio
        pen_bg = QPen(QColor(TEMA["card_border"]), 12)
        pen_bg.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_bg)
        painter.drawArc(draw_rect, 0, 360 * 16)

        # Arco del progresso
        pen_fg = QPen(self.color, 12)
        pen_fg.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_fg)
        span_angle = int(-self.value * 3.6 * 16)
        painter.drawArc(draw_rect, 90 * 16, span_angle)

        # Testo percentuale al centro
        painter.setPen(QColor(TEMA["text_main"]))
        font = painter.font()
        font.setPointSize(16)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{self.value}%")

        # Titolo in basso
        font.setPointSize(9)
        font.setBold(False)
        painter.setFont(font)
        title_rect = rect.adjusted(0, int(size/2 + 25), 0, 0)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, self.title)

        painter.end()

class AssistantGUI(QMainWindow):
    def __init__(self, gui_queue, on_send_text_callback, on_toggle_mute_callback, on_exit_callback, on_settings_saved_callback=None, on_stop_tts_callback=None, on_state_change_callback=None, on_new_chat_callback=None):
        super().__init__()
        self.gui_queue = gui_queue
        self.on_send_text = on_send_text_callback
        self.on_toggle_mute = on_toggle_mute_callback
        self.on_exit = on_exit_callback
        self.on_settings_saved = on_settings_saved_callback
        self.on_stop_tts = on_stop_tts_callback
        self.on_state_change = on_state_change_callback
        self.on_new_chat = on_new_chat_callback

        self.config_data = load_config()
        self.is_muted = False
        self._current_state = "muted"
        self.sidebar_collapsed = False

        self._pulse_angle = 0.0
        self._chat_status_dots_count = 0

        self._typewriter_queue = []
        self._processing_typewriter = False

        self.setWindowTitle("OmniMind - Assistente Virtuale")
        self.resize(850, 750)
        self.setMinimumSize(800, 700)

        # Sostituisce il protocol("WM_DELETE_WINDOW")

        self._apply_theme()
        self._create_layout()
        self._populate_settings_fields()

        self.show_screen("chat")

        # QTimer polling queue
        self.queue_timer = QTimer(self)
        self.queue_timer.timeout.connect(self.check_queue)
        self.queue_timer.start(100)

        # Status animation timers
        self.pulse_timer = QTimer(self)
        self.pulse_timer.timeout.connect(self._pulse_status_circle)

        self.chat_status_timer = QTimer(self)
        self.chat_status_timer.timeout.connect(self._animate_chat_status)

    def closeEvent(self, event):
        """Minimize to tray instead of closing"""
        event.ignore()
        self.minimize_to_tray()

    def _apply_theme(self):
        theme_mode = self.config_data.get("theme", "Scuro")
        accent_name = self.config_data.get("accent_color", "Azzurro")

        accents = {
            "Azzurro": "#38bdf8", "Rosso": "#ef4444",
            "Verde": "#10b981", "Viola": "#8b5cf6", "Arancione": "#f59e0b"
        }
        accent = accents.get(accent_name, "#38bdf8")

        if theme_mode == "Chiaro":
            bg_main = "#f8fafc"
            bg_sidebar = "#f1f5f9"
            bg_hover = "#e2e8f0"
            bg_input = "#ffffff"
            text_main = "#0f172a"
            text_dim = "#64748b"
            card_border = "#e2e8f0"
            card_bg = "#ffffff"
            input_border = "#cbd5e1"
            scroll_handle = "#cbd5e1"
        else:
            bg_main = "#0f172a"
            bg_sidebar = "#1e293b"
            bg_hover = "#334155"
            bg_input = "#020617"
            text_main = "#f8fafc"
            text_dim = "#94a3b8"
            card_border = "#1e293b"
            card_bg = "#1e293b"
            input_border = "#334155"
            scroll_handle = "#475569"

        # Rende la palette disponibile a chi disegna fuori dal foglio di stile
        # (chat in HTML, cronologia, log, donut della dashboard).
        TEMA.update({
            "bg_main": bg_main,
            "card_bg": card_bg,
            "card_border": card_border,
            "text_main": text_main,
            "text_dim": text_dim,
            "accent": accent,
            "utente": "#2563eb" if theme_mode == "Chiaro" else "#60a5fa",
            "assistente": "#047857" if theme_mode == "Chiaro" else "#10b981",
        })

        self.setStyleSheet(f"""
            QMainWindow, QWidget#content_container, QScrollArea, QScrollArea > QWidget > QWidget {{
                background-color: {bg_main};
                color: {text_main};
                font-family: "Segoe UI", "Roboto", sans-serif;
            }}
            QFrame#sidebar {{
                background-color: {bg_sidebar};
                border-right: 1px solid {card_border};
            }}
            QLabel {{ color: {text_main}; font-family: "Segoe UI", "Roboto", sans-serif; }}
            QLabel#logo_label {{ color: {accent}; font-size: 22px; font-weight: 800; letter-spacing: 1px; }}
            QLabel#status_label {{ color: {text_dim}; font-size: 12px; }}
            QLabel#chat_status_label {{ color: {text_dim}; font-size: 12px; font-style: italic; }}
            QLabel#section_title {{ font-size: 24px; font-weight: bold; margin-bottom: 10px; }}

            QPushButton {{
                background-color: transparent;
                color: {text_main};
                text-align: left;
                padding: 12px 15px;
                border: none;
                font-weight: 600;
                font-size: 14px;
                border-radius: 8px;
            }}
            QPushButton:hover {{ background-color: {bg_hover}; }}
            QPushButton:checked {{ background-color: {bg_hover}; color: {accent}; font-weight: bold; }}

            QPushButton#toggle_btn {{ font-size: 18px; padding: 5px; width: 35px; border-radius: 8px; text-align: center; }}

            QPushButton#mute_btn {{
                background-color: {bg_hover};
                color: {text_main};
                text-align: center;
                font-size: 13px;
                font-weight: bold;
                border-radius: 8px;
            }}
            QPushButton#mute_btn:hover {{ background-color: {card_border}; border: 1px solid {accent}; }}

            QPushButton#send_btn, QPushButton#save_btn {{
                background-color: {accent};
                text-align: center;
                border-radius: 8px;
                color: #ffffff;
                font-weight: bold;
                font-size: 14px;
                padding: 10px;
            }}
            QPushButton#send_btn:hover, QPushButton#save_btn:hover {{ background-color: {bg_main}; border: 2px solid {accent}; color: {accent}; }}

            QPushButton#restart_btn {{
                background-color: transparent;
                color: #ef4444;
                border: 1px solid #7f1d1d;
                border-radius: 8px;
                margin-top: 5px;
                text-align: center;
            }}
            QPushButton#restart_btn:hover {{ background-color: #ef4444; color: white; border: none; }}

            QTextEdit, QLineEdit {{
                background-color: {bg_input};
                color: {text_main};
                border: 1px solid {input_border};
                border-radius: 10px;
                font-size: 14px;
                padding: 12px;
            }}
            QTextEdit:focus, QLineEdit:focus {{ border: 1px solid {accent}; }}

            QSlider::groove:horizontal {{
                border: none;
                height: 6px;
                background: {bg_main};
                border-radius: 3px;
            }}
            QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 3px; }}
            QSlider::handle:horizontal {{
                background: {text_main};
                border: 2px solid {accent};
                width: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }}

            QComboBox, QSpinBox {{
                background-color: {bg_input};
                border: 1px solid {input_border};
                border-radius: 8px;
                padding: 8px 12px;
                color: {text_main};
                font-size: 13px;
            }}
            QComboBox::drop-down {{ border: none; width: 30px; }}

            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {scroll_handle};
                min-height: 30px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {accent}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ border: none; background: none; height: 0px; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

            QFrame#card {{
                background-color: {card_bg};
                border: 1px solid {card_border};
                border-radius: 12px;
            }}

            QCheckBox {{
                color: {text_main};
                font-size: 13px;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid {input_border};
                background-color: {bg_input};
            }}
            QCheckBox::indicator:checked {{
                background-color: {accent};
                border: 1px solid {accent};
            }}
        """)

    def _create_layout(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # ----------------- SIDEBAR -----------------
        self.sidebar_frame = QFrame()
        self.sidebar_frame.setObjectName("sidebar")
        self.sidebar_frame.setFixedWidth(220)
        self.sidebar_layout = QVBoxLayout(self.sidebar_frame)
        self.sidebar_layout.setContentsMargins(10, 20, 10, 20)

        self.logo_layout = QHBoxLayout()
        self.logo_label = QLabel("OMNIMIND")
        self.logo_label.setObjectName("logo_label")
        self.toggle_sidebar_btn = QPushButton("☰")
        self.toggle_sidebar_btn.setObjectName("toggle_btn")
        self.toggle_sidebar_btn.setFixedSize(30, 30)
        self.toggle_sidebar_btn.clicked.connect(self.toggle_sidebar)
        self.logo_layout.addWidget(self.logo_label)
        self.logo_layout.addStretch()
        self.logo_layout.addWidget(self.toggle_sidebar_btn)
        self.sidebar_layout.addLayout(self.logo_layout)

        self.status_layout = QHBoxLayout()
        self.status_circle = StatusCircle()
        self.status_label = QLabel("Avvio...")
        self.status_label.setObjectName("status_label")
        self.status_layout.addWidget(self.status_circle)
        self.status_layout.addWidget(self.status_label)
        self.status_layout.addStretch()
        self.sidebar_layout.addLayout(self.status_layout)
        self.sidebar_layout.addSpacing(20)

        self.nav_btns = []

        self.chat_nav_btn = self._create_nav_btn("💬  Chat", "chat")
        self.settings_nav_btn = self._create_nav_btn("⚙️  Impostazioni", "settings")
        self.modes_nav_btn = self._create_nav_btn("🎯  Profili / Modalità", "modes")
        self.instructions_nav_btn = self._create_nav_btn("📖  Guida Comandi", "instructions")
        self.logs_nav_btn = self._create_nav_btn("📊  Log di Sistema", "logs")
        self.dashboard_nav_btn = self._create_nav_btn("🖥️  Dashboard Hardware", "dashboard")
        self.plugins_nav_btn = self._create_nav_btn("🧩  Gestione Plugin", "plugins")
        self.history_nav_btn = self._create_nav_btn("📜  Cronologia Vecchia", "history")

        self.sidebar_layout.addStretch()

        self.mute_btn = QPushButton("🎤 Disattiva Vocale")
        self.mute_btn.setObjectName("mute_btn")
        self.mute_btn.setFixedHeight(35)
        self.mute_btn.clicked.connect(self.toggle_mute)
        self.sidebar_layout.addWidget(self.mute_btn)

        self.restart_btn = QPushButton("🔄 Riavvia OmniMind")
        self.restart_btn.setObjectName("restart_btn")
        self.restart_btn.setFixedHeight(35)
        self.restart_btn.setStyleSheet("""
            QPushButton { background-color: #7f1d1d; color: #f87171; border: 1px solid #991b1b; border-radius: 5px; margin-top: 5px;}
            QPushButton:hover { background-color: #991b1b; color: white; }
        """)
        self.restart_btn.clicked.connect(self.restart_app)
        self.sidebar_layout.addWidget(self.restart_btn)

        # ----------------- CONTENT CONTAINER -----------------
        self.content_container = QStackedWidget()
        self.content_container.setObjectName("content_container")

        self.main_layout.addWidget(self.sidebar_frame)
        self.main_layout.addWidget(self.content_container, 1)

        self._build_chat_screen()
        self._build_settings_screen()
        self._build_modes_screen()
        self._build_instructions_screen()
        self._build_logs_screen()
        self._build_dashboard_screen()
        self._build_plugins_screen()
        self._build_history_screen()

        # Add screens to stacked widget
        self.screens = {
            "chat": self.chat_screen,
            "settings": self.settings_screen,
            "modes": self.modes_screen,
            "instructions": self.instructions_screen,
            "logs": self.logs_screen,
            "dashboard": self.dashboard_screen,
            "plugins": self.plugins_screen,
            "history": self.history_screen
        }
        for name, widget in self.screens.items():
            self.content_container.addWidget(widget)

    def _create_nav_btn(self, text, screen_name):
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setFixedHeight(40)
        btn.clicked.connect(lambda: self.show_screen(screen_name))
        self.sidebar_layout.addWidget(btn)
        self.nav_btns.append((btn, text, screen_name))
        return btn



    def _create_card(self, title_text):
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        title = QLabel(title_text)
        title.setStyleSheet("color: #38bdf8; font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        return card, layout

    def _build_chat_screen(self):
        self.chat_screen = QWidget()
        layout = QVBoxLayout(self.chat_screen)
        layout.setContentsMargins(15, 15, 15, 15)

        self.chat_log = QTextEdit()
        self.chat_log.setReadOnly(True)
        layout.addWidget(self.chat_log, 1)

        self.chat_status_label = QLabel("")
        self.chat_status_label.setObjectName("chat_status_label")
        layout.addWidget(self.chat_status_label)

        input_layout = QHBoxLayout()
        self.entry_box = QLineEdit()
        self.entry_box.setPlaceholderText("Invia un messaggio o digita un comando...")
        self.entry_box.setFixedHeight(45)
        self.entry_box.returnPressed.connect(self.send_message)

        self.send_btn = QPushButton("Invia")
        self.send_btn.setObjectName("send_btn")
        self.send_btn.setFixedSize(80, 45)
        self.send_btn.clicked.connect(self.send_message)

        self.stop_tts_btn = QPushButton("⏹️")
        self.stop_tts_btn.setObjectName("send_btn")
        self.stop_tts_btn.setFixedSize(45, 45)
        self.stop_tts_btn.setToolTip("Interrompi la voce")
        self.stop_tts_btn.clicked.connect(self._handle_stop_tts)

        # Azzera il contesto inviato al modello: reset_chat() esisteva ma non
        # era richiamata da nessuna parte, quindi la cronologia cresceva per
        # tutta la sessione senza alcun modo di ripartire da zero.
        self.new_chat_btn = QPushButton("🧹")
        self.new_chat_btn.setObjectName("send_btn")
        self.new_chat_btn.setFixedSize(45, 45)
        self.new_chat_btn.setToolTip("Nuova conversazione (azzera il contesto)")
        self.new_chat_btn.clicked.connect(self._handle_new_chat)

        input_layout.addWidget(self.entry_box, 1)
        input_layout.addWidget(self.new_chat_btn)
        input_layout.addWidget(self.stop_tts_btn)
        input_layout.addWidget(self.send_btn)
        layout.addLayout(input_layout)

    def _handle_stop_tts(self):
        if self.on_stop_tts:
            self.on_stop_tts()

    def _handle_new_chat(self):
        if self.on_new_chat:
            self.on_new_chat()
        self.chat_log.clear()
        self.add_system_message("Nuova conversazione: il contesto precedente e' stato azzerato.")

    def _build_settings_screen(self):
        self.settings_screen = QScrollArea()
        self.settings_screen.setWidgetResizable(True)
        self.settings_screen.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)

        title = QLabel("Configurazione Avanzata")
        title.setObjectName("section_title")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(20)

        # --- Card 1: Intelligenza Artificiale ---
        ai_card, ai_layout_v = self._create_card("🧠 Intelligenza Artificiale")
        ai_layout = QFormLayout()
        self.key_entry = QLineEdit()
        self.key_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_entry.setMaximumWidth(250)
        ai_layout.addRow("Gemini API Key:", self.key_entry)

        self.model_combo = QComboBox()
        self.model_combo.addItems(["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-1.5-pro"])
        self.model_combo.setMaximumWidth(250)
        ai_layout.addRow("Modello AI:", self.model_combo)

        self.temp_slider = QSlider(Qt.Orientation.Horizontal)
        self.temp_slider.setRange(0, 10)
        self.temp_slider.setMaximumWidth(250)
        ai_layout.addRow("Creatività (Temp):", self.temp_slider)
        ai_layout_v.addLayout(ai_layout)
        grid.addWidget(ai_card, 0, 0)

        # --- Card 2: Hardware & Voce ---
        hw_card, hw_layout_v = self._create_card("🎙️ Hardware & Voce")
        hw_layout = QFormLayout()
        self.wakeword_entry = QLineEdit()
        self.wakeword_entry.setMaximumWidth(250)
        hw_layout.addRow("Wake-Word:", self.wakeword_entry)

        self.tts_engine_combo = QComboBox()
        self.tts_engine_combo.addItems(["Microsoft Edge (Gratis)", "ElevenLabs", "OpenAI"])
        self.tts_engine_combo.setMaximumWidth(250)
        hw_layout.addRow("Motore vocale:", self.tts_engine_combo)

        self.voice_combo = QComboBox()
        self.voice_combo.addItems(["it-IT-GiuseppeNeural", "it-IT-ElsaNeural", "it-IT-DiegoNeural"])
        self.voice_combo.setMaximumWidth(250)
        hw_layout.addRow("Voce (Edge):", self.voice_combo)

        self.mic_slider = QSlider(Qt.Orientation.Horizontal)
        self.mic_slider.setRange(100, 2000)
        self.mic_slider.setMaximumWidth(250)
        hw_layout.addRow("Soglia Rumore Mic:", self.mic_slider)
        hw_layout_v.addLayout(hw_layout)
        grid.addWidget(hw_card, 0, 1)

        # --- Card 3: Aspetto & Sistema ---
        sys_card, sys_layout_v = self._create_card("⚙️ Aspetto & Sistema")
        sys_layout = QFormLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Scuro", "Chiaro"])
        self.theme_combo.setMaximumWidth(250)
        sys_layout.addRow("Tema:", self.theme_combo)

        self.accent_combo = QComboBox()
        self.accent_combo.addItems(["Azzurro", "Rosso", "Verde", "Viola", "Arancione"])
        self.accent_combo.setMaximumWidth(250)
        sys_layout.addRow("Accento:", self.accent_combo)
        sys_layout_v.addLayout(sys_layout)

        self.windows_start_cb = QCheckBox("Avvia con Windows")
        sys_layout_v.addWidget(self.windows_start_cb)

        self.minimize_start_cb = QCheckBox("Avvia minimizzato")
        sys_layout_v.addWidget(self.minimize_start_cb)
        grid.addWidget(sys_card, 1, 0)

        # --- Card 4: Automazione RPA ---
        rpa_card, rpa_layout_v = self._create_card("🤖 Automazione (RPA)")
        rpa_layout = QFormLayout()
        self.rpa_delay_combo = QComboBox()
        self.rpa_delay_combo.addItems(["Lento (Sicuro)", "Normale", "Fulmineo"])
        self.rpa_delay_combo.setMaximumWidth(250)
        rpa_layout.addRow("Velocità Digitazione:", self.rpa_delay_combo)
        rpa_layout_v.addLayout(rpa_layout)

        self.rpa_enter_cb = QCheckBox("Premi 'Invio' in automatico dopo aver digitato")
        rpa_layout_v.addWidget(self.rpa_enter_cb)
        grid.addWidget(rpa_card, 1, 1)

        # --- Card 5: Integrazioni API ---
        api_card, api_layout_v = self._create_card("🌐 Integrazioni e Servizi Esterni")
        api_layout = QFormLayout()
        self.spotify_id_entry = QLineEdit()
        self.spotify_id_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.spotify_id_entry.setMaximumWidth(250)
        api_layout.addRow("Spotify Client ID:", self.spotify_id_entry)

        self.spotify_secret_entry = QLineEdit()
        self.spotify_secret_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.spotify_secret_entry.setMaximumWidth(250)
        api_layout.addRow("Spotify Secret:", self.spotify_secret_entry)

        self.eleven_key_entry = QLineEdit()
        self.eleven_key_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.eleven_key_entry.setMaximumWidth(250)
        api_layout.addRow("ElevenLabs API Key:", self.eleven_key_entry)

        self.eleven_voice_entry = QLineEdit()
        self.eleven_voice_entry.setMaximumWidth(250)
        api_layout.addRow("ElevenLabs Voice ID:", self.eleven_voice_entry)

        self.openai_key_entry = QLineEdit()
        self.openai_key_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_key_entry.setMaximumWidth(250)
        api_layout.addRow("OpenAI API Key:", self.openai_key_entry)

        self.openai_voice_combo = QComboBox()
        self.openai_voice_combo.addItems(["alloy", "echo", "fable", "onyx", "nova", "shimmer"])
        self.openai_voice_combo.setMaximumWidth(250)
        api_layout.addRow("Voce OpenAI:", self.openai_voice_combo)
        api_layout_v.addLayout(api_layout)
        grid.addWidget(api_card, 2, 0, 1, 2)

        # --- Card 6: Sicurezza & Dati ---
        sec_card, sec_layout_v = self._create_card("🛡️ Sicurezza & Gestione Dati")
        self.safe_mode_cb = QCheckBox("Safe Mode: Chiedi conferma vocale prima di eseguire comandi irreversibili")
        sec_layout_v.addWidget(self.safe_mode_cb)

        sec_layout = QFormLayout()
        self.log_combo = QComboBox()
        self.log_combo.addItems(["Debug", "Info", "Error"])
        self.log_combo.setMaximumWidth(250)
        sec_layout.addRow("Livello di Log:", self.log_combo)
        sec_layout_v.addLayout(sec_layout)

        self.hotkey_entry = QLineEdit()
        self.hotkey_entry.setMaximumWidth(250)
        self.hotkey_entry.setPlaceholderText("vuoto = disattivata")
        sec_layout.addRow("Hotkey analisi appunti:", self.hotkey_entry)

        self.clear_cache_btn = QPushButton("🗑️ Svuota Cache")
        self.clear_cache_btn.setStyleSheet("background-color: #ef4444; color: white; border: none; font-weight: bold; border-radius: 5px;")
        self.clear_cache_btn.clicked.connect(self.clear_assistant_cache)
        self.clear_cache_btn.setMaximumWidth(150)
        sec_layout_v.addWidget(self.clear_cache_btn)

        grid.addWidget(sec_card, 3, 0, 1, 2)

        layout.addLayout(grid)
        layout.addSpacing(20)

        save_btn = QPushButton("💾 Salva Configurazioni")
        save_btn.setFixedHeight(45)
        save_btn.setMaximumWidth(300)
        save_btn.setStyleSheet("background-color: #38bdf8; color: #0f172a; font-weight: bold; border-radius: 5px;")
        save_btn.clicked.connect(self.save_settings)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addStretch()
        self.settings_screen.setWidget(content)

    def _build_modes_screen(self):
        self.modes_screen = QScrollArea()
        self.modes_screen.setWidgetResizable(True)
        self.modes_screen.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)

        title = QLabel("Gestore Profili & Automazioni")
        title.setObjectName("section_title")
        layout.addWidget(title)

        # --- Card 1: Profilo Attivo ---
        active_card, active_layout_v = self._create_card("🌟 Profilo di Sistema Attivo")
        active_layout = QFormLayout()
        self.profile_menu = QComboBox()
        self.profile_menu.addItems(["Nessuno", "Focus / Studio", "Gaming", "Notte / Relax"])
        self.profile_menu.setMaximumWidth(250)
        self.profile_menu.currentTextChanged.connect(self.on_profile_selected)
        active_layout.addRow("Seleziona Profilo (applica subito):", self.profile_menu)
        active_layout_v.addLayout(active_layout)
        layout.addWidget(active_card)

        grid = QGridLayout()
        grid.setSpacing(20)

        # --- Card 2: Focus / Studio ---
        focus_card, focus_layout_v = self._create_card("📚 Profilo Focus / Studio")
        self.focus_mute_tts_check = QCheckBox("Silenzia risposte vocali (TTS)")
        self.focus_close_apps_check = QCheckBox("Termina app distrattive all'avvio")
        self.focus_block_notifications_check = QCheckBox("Silenzia notifiche desktop")
        self.focus_pomodoro_check = QCheckBox("Avvia Timer Pomodoro (25min)")
        self.focus_lofi_check = QCheckBox("Riproduci Playlist Lo-Fi (Spotify)")
        focus_layout_v.addWidget(self.focus_mute_tts_check)
        focus_layout_v.addWidget(self.focus_close_apps_check)
        focus_layout_v.addWidget(self.focus_block_notifications_check)
        focus_layout_v.addWidget(self.focus_pomodoro_check)
        focus_layout_v.addWidget(self.focus_lofi_check)
        grid.addWidget(focus_card, 0, 0)

        # --- Card 3: Gaming ---
        gaming_card, gaming_layout_v = self._create_card("🎮 Profilo Gaming")
        gv_layout = QHBoxLayout()
        gv_layout.addWidget(QLabel("Volume in gioco:"))
        self.gaming_volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.gaming_volume_slider.setRange(0, 100)
        self.gaming_vol_pct_label = QLabel("30%")
        self.gaming_vol_pct_label.setFixedWidth(40)
        gv_layout.addWidget(self.gaming_volume_slider)
        gv_layout.addWidget(self.gaming_vol_pct_label)
        gaming_layout_v.addLayout(gv_layout)

        self.gaming_open_launchers_check = QCheckBox("Avvia automaticamente launcher")
        self.gaming_optimize_ram_check = QCheckBox("Ottimizza RAM liberando cache")
        self.gaming_power_check = QCheckBox("Attiva Piano Prestazioni Eccellenti")
        self.gaming_kill_browsers_check = QCheckBox("Forza chiusura browser pesanti")
        gaming_layout_v.addWidget(self.gaming_open_launchers_check)
        gaming_layout_v.addWidget(self.gaming_optimize_ram_check)
        gaming_layout_v.addWidget(self.gaming_power_check)
        gaming_layout_v.addWidget(self.gaming_kill_browsers_check)
        grid.addWidget(gaming_card, 0, 1)

        # --- Card 4: Notte / Relax ---
        night_card, night_layout_v = self._create_card("🌙 Profilo Notte / Relax")
        nv_layout = QHBoxLayout()
        nv_layout.addWidget(QLabel("Volume Notturno:"))
        self.night_volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.night_volume_slider.setRange(0, 100)
        self.night_vol_pct_label = QLabel("15%")
        self.night_vol_pct_label.setFixedWidth(40)
        nv_layout.addWidget(self.night_volume_slider)
        nv_layout.addWidget(self.night_vol_pct_label)
        night_layout_v.addLayout(nv_layout)

        nb_layout = QHBoxLayout()
        nb_layout.addWidget(QLabel("Luminosità Schermo:"))
        self.night_bright_slider = QSlider(Qt.Orientation.Horizontal)
        self.night_bright_slider.setRange(0, 100)
        self.night_bright_pct_label = QLabel("15%")
        self.night_bright_pct_label.setFixedWidth(40)
        nb_layout.addWidget(self.night_bright_slider)
        nb_layout.addWidget(self.night_bright_pct_label)
        night_layout_v.addLayout(nb_layout)

        self.night_blue_light_check = QCheckBox("Attiva Filtro Luce Blu (Windows)")
        night_layout_v.addWidget(self.night_blue_light_check)

        sl_layout = QHBoxLayout()
        sl_layout.addWidget(QLabel("Timer Auto-Spegnimento:"))
        self.night_sleep_timer = QComboBox()
        self.night_sleep_timer.addItems(["Mai", "30 min", "1 ora", "2 ore"])
        self.night_sleep_timer.setMaximumWidth(150)
        sl_layout.addWidget(self.night_sleep_timer)
        night_layout_v.addLayout(sl_layout)
        grid.addWidget(night_card, 1, 0)

        # --- Card 5: Standard / Quotidiano ---
        std_card, std_layout_v = self._create_card("☀️ Profilo Standard / Sveglia")
        av_layout = QHBoxLayout()
        av_layout.addWidget(QLabel("Volume Sveglia:"))
        self.alarm_volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.alarm_volume_slider.setRange(0, 100)
        self.alarm_vol_pct_label = QLabel("50%")
        self.alarm_vol_pct_label.setFixedWidth(40)
        av_layout.addWidget(self.alarm_volume_slider)
        av_layout.addWidget(self.alarm_vol_pct_label)
        std_layout_v.addLayout(av_layout)

        sb_layout = QHBoxLayout()
        sb_layout.addWidget(QLabel("Luminosità Standard:"))
        self.std_bright_slider = QSlider(Qt.Orientation.Horizontal)
        self.std_bright_slider.setRange(0, 100)
        self.std_bright_pct_label = QLabel("80%")
        self.std_bright_pct_label.setFixedWidth(40)
        sb_layout.addWidget(self.std_bright_slider)
        sb_layout.addWidget(self.std_bright_pct_label)
        std_layout_v.addLayout(sb_layout)
        grid.addWidget(std_card, 1, 1)

        # --- Card 6: Trigger Automatici ---
        trigger_card, trigger_layout_v = self._create_card("⚡ Trigger di Auto-Attivazione")
        trigger_layout = QFormLayout()
        self.trigger_time_night = QLineEdit()
        self.trigger_time_night.setPlaceholderText("Es. 23:00")
        self.trigger_time_night.setMaximumWidth(150)
        trigger_layout.addRow("Attiva 'Notte' alle ore:", self.trigger_time_night)

        self.trigger_app_gaming = QLineEdit()
        self.trigger_app_gaming.setPlaceholderText("Es. steam.exe")
        self.trigger_app_gaming.setMaximumWidth(250)
        trigger_layout.addRow("Attiva 'Gaming' se apro l'app:", self.trigger_app_gaming)
        trigger_layout_v.addLayout(trigger_layout)
        grid.addWidget(trigger_card, 2, 0, 1, 2)

        layout.addLayout(grid)
        layout.addSpacing(20)

        save_btn = QPushButton("💾 Salva Configurazioni Profili")
        save_btn.setFixedHeight(45)
        save_btn.setMaximumWidth(300)
        save_btn.setObjectName("save_btn")
        save_btn.clicked.connect(self.save_profile_settings)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addStretch()
        self.modes_screen.setWidget(content)

        # Connessioni segnali per le label dei valori
        self.gaming_volume_slider.valueChanged.connect(self.on_gaming_volume_slider_move)
        self.night_volume_slider.valueChanged.connect(lambda v: self.night_vol_pct_label.setText(f"{v}%"))
        self.night_bright_slider.valueChanged.connect(lambda v: self.night_bright_pct_label.setText(f"{v}%"))
        self.alarm_volume_slider.valueChanged.connect(lambda v: self.alarm_vol_pct_label.setText(f"{v}%"))
        self.std_bright_slider.valueChanged.connect(lambda v: self.std_bright_pct_label.setText(f"{v}%"))

    def _build_dashboard_screen(self):

        self.dashboard_screen = QScrollArea()
        self.dashboard_screen.setWidgetResizable(True)
        self.dashboard_screen.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)

        title = QLabel("Telemetry & Hardware Dashboard")
        title.setObjectName("section_title")
        layout.addWidget(title)

        # --- Donut Charts Grid (Dynamic) ---
        donut_group = QGroupBox("Utilizzo Risorse (Real-Time)")
        donut_layout = QGridLayout()

        self.donuts = {} # Dizionario per tracciare i widget dinamici dei dischi

        self.cpu_donut = DonutProgressWidget(color="#38bdf8", title="CPU")
        self.ram_donut = DonutProgressWidget(color="#10b981", title="RAM")
        donut_layout.addWidget(self.cpu_donut, 0, 0)
        donut_layout.addWidget(self.ram_donut, 0, 1)

        col = 2
        row = 0

        # Generazione Dinamica Dischi
        colors = ["#8b5cf6", "#f43f5e", "#f59e0b", "#ec4899", "#14b8a6"]
        color_idx = 0
        for partition in psutil.disk_partitions():
            if 'cdrom' in partition.opts or partition.fstype == '':
                continue
            drive_letter = partition.device.replace("\\", "")
            donut = DonutProgressWidget(color=colors[color_idx % len(colors)], title=f"Disco ({drive_letter})")
            self.donuts[partition.device] = donut

            donut_layout.addWidget(donut, row, col)
            col += 1
            if col > 3:
                col = 0
                row += 1
            color_idx += 1

        donut_group.setLayout(donut_layout)
        layout.addWidget(donut_group)

        # --- Advanced Telemetry Grid ---
        info_grid = QGridLayout()
        info_grid.setSpacing(20)

        # CPU & RAM Avanzate
        hw_group = QGroupBox("🧠 Dettagli Core & Memoria")
        hw_layout = QVBoxLayout()
        self.cpu_freq_label = QLabel("Frequenza CPU: Calcolo...")
        self.cpu_cores_label = QLabel(f"Core (Logici/Fisici): {psutil.cpu_count(logical=True)} / {psutil.cpu_count(logical=False)}")
        self.ram_detail_label = QLabel("RAM Totale: Calcolo...")
        hw_layout.addWidget(self.cpu_freq_label)
        hw_layout.addWidget(self.cpu_cores_label)
        hw_layout.addWidget(self.ram_detail_label)
        hw_group.setLayout(hw_layout)
        info_grid.addWidget(hw_group, 0, 0)

        # GPU & Rete
        ext_group = QGroupBox("🎮 GPU & Rete")
        ext_layout = QVBoxLayout()
        self.gpu_info_label = QLabel("GPU: Ricerca in corso...")
        self.net_down_label = QLabel("Download: 0.0 Mbps")
        self.net_up_label = QLabel("Upload: 0.0 Mbps")
        self.net_down_label.setStyleSheet("color: #38bdf8; font-weight: bold;")
        self.net_up_label.setStyleSheet("color: #10b981; font-weight: bold;")
        ext_layout.addWidget(self.gpu_info_label)
        ext_layout.addWidget(self.net_down_label)
        ext_layout.addWidget(self.net_up_label)
        ext_group.setLayout(ext_layout)
        info_grid.addWidget(ext_group, 0, 1)

        layout.addLayout(info_grid)
        layout.addStretch()

        self.last_net_io = None
        import time
        self.last_net_time = time.time()

        # Avvia thread asincrono per la lettura CPU identica a Task Manager
        import threading
        import subprocess
        self.wmi_cpu_usage = 0

        self._wmi_poll_running = False
        self._wmi_thread = None

        def poll_wmi_cpu():
            import time
            while self._wmi_poll_running:
                try:
                    res = subprocess.run(
                        ["wmic", "cpu", "get", "loadpercentage"],
                        capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    lines = [x.strip() for x in res.stdout.strip().split('\n') if x.strip()]
                    if len(lines) >= 2:
                        self.wmi_cpu_usage = int(lines[1])
                except Exception:
                    pass
                time.sleep(1.5)

        # Il thread non parte piu' alla costruzione della GUI: veniva avviato
        # sempre, anche senza mai aprire la Dashboard, e non veniva mai fermato.
        self._avvia_poll_wmi = lambda: self._start_wmi_thread(poll_wmi_cpu)

        self.dashboard_screen.setWidget(content)

        self.dashboard_timer = QTimer(self)
        self.dashboard_timer.timeout.connect(self._update_dashboard_stats)

    def _start_wmi_thread(self, target):
        """Avvia il polling CPU solo alla prima apertura della Dashboard."""
        if self._wmi_thread is not None and self._wmi_thread.is_alive():
            return
        import threading
        self._wmi_poll_running = True
        self._wmi_thread = threading.Thread(target=target, daemon=True)
        self._wmi_thread.start()

    def shutdown(self):
        """Ferma timer e thread di background. Chiamato in fase di uscita."""
        self._wmi_poll_running = False
        for nome in ("queue_timer", "pulse_timer", "chat_status_timer", "dashboard_timer"):
            timer = getattr(self, nome, None)
            if timer is not None:
                try:
                    timer.stop()
                except Exception:
                    pass

    def _update_dashboard_stats(self):
        # Lettura CPU da WMI (Stesso identico valore di Task Manager)
        self.cpu_donut.setValue(self.wmi_cpu_usage)

        try:
            freq = psutil.cpu_freq()
            if freq:
                self.cpu_freq_label.setText(f"Frequenza CPU: {freq.current:.0f} MHz (Max {freq.max:.0f} MHz)")
        except Exception:
            pass

        # RAM
        ram = psutil.virtual_memory()
        self.ram_donut.setValue(int(ram.percent))
        self.ram_detail_label.setText(f"RAM: {ram.used / (1024**3):.1f} GB usati su {ram.total / (1024**3):.1f} GB")

        # Dischi Multipli Dinamici
        for device, donut in self.donuts.items():
            try:
                disk = psutil.disk_usage(device)
                donut.setValue(int(disk.percent))
            except Exception:
                pass

        # Traffico di Rete (Delta calculation)
        net_io = psutil.net_io_counters()
        current_time = time.time()

        if self.last_net_io is not None:
            time_delta = current_time - self.last_net_time
            if time_delta > 0:
                down_bytes = net_io.bytes_recv - self.last_net_io.bytes_recv
                up_bytes = net_io.bytes_sent - self.last_net_io.bytes_sent

                down_mbps = (down_bytes * 8) / (1024 * 1024 * time_delta)
                up_mbps = (up_bytes * 8) / (1024 * 1024 * time_delta)

                self.net_down_label.setText(f"Download: {down_mbps:.2f} Mbps")
                self.net_up_label.setText(f"Upload: {up_mbps:.2f} Mbps")

        self.last_net_io = net_io
        self.last_net_time = current_time

        # GPU Telemetry (Nvidia-SMI nativo per evitare popup CMD)
        try:
            import subprocess
            res = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=2,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if res.returncode == 0 and res.stdout.strip():
                parts = res.stdout.strip().split(", ")
                if len(parts) >= 5:
                    name, util, temp, mem_used, mem_tot = parts[0], parts[1], parts[2], parts[3], parts[4]
                    self.gpu_info_label.setText(f"GPU: {name}\nCarico GPU: {util}\nTemperatura: {temp}°C\nVRAM Usata: {mem_used} / {mem_tot}")
            else:
                self.gpu_info_label.setText("GPU: Nessuna GPU Nvidia rilevata")
        except Exception:
            self.gpu_info_label.setText("GPU: Non disponibile")

    def _build_instructions_screen(self):
        """
        Guida comandi generata dai plugin attivi.

        Prima era una lista scritta a mano di nove voci che non corrispondeva
        piu' ai comandi realmente riconosciuti: elencava funzioni inesistenti e
        ne ometteva molte. Ora ogni plugin dichiara i propri esempi, quindi la
        guida resta vera per costruzione e mostra solo i plugin abilitati.
        """
        self.instructions_screen = QScrollArea()
        self.instructions_screen.setWidgetResizable(True)
        self.instructions_screen.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)

        title = QLabel("Manuale dei Comandi")
        title.setObjectName("section_title")
        layout.addWidget(title)

        ww = self.config_data.get("wake_word", "omnimind")
        layout.addWidget(QLabel(
            f"Interagisci vocalmente dicendo \"{ww} [comando]\" oppure scrivendo nella chat."))

        try:
            from src.commands import _plugin_manager
            attivi = sorted(_plugin_manager.plugins, key=lambda p: p.priority)
        except Exception as e:
            logger.error(f"Impossibile leggere i plugin per la guida comandi: {e}")
            attivi = []

        for plugin in attivi:
            esempi = getattr(plugin, "examples", []) or []
            if not esempi:
                continue

            card = QFrame()
            card.setObjectName("card")
            cl = QVBoxLayout(card)

            tl = QLabel(plugin.name)
            tl.setStyleSheet(f"color: {TEMA['accent']}; font-weight: bold; font-size: 15px;")
            cl.addWidget(tl)

            dl = QLabel(plugin.description)
            dl.setWordWrap(True)
            dl.setStyleSheet(f"color: {TEMA['text_dim']};")
            cl.addWidget(dl)

            for frase, descrizione in esempi:
                riga = QLabel(f"<b>\u2022 \"{frase}\"</b> — {descrizione}")
                riga.setWordWrap(True)
                riga.setStyleSheet(f"color: {TEMA['text_main']}; margin-left: 8px;")
                cl.addWidget(riga)

            layout.addWidget(card)

        if not attivi:
            avviso = QLabel("Nessun plugin attivo: abilitane almeno uno da 'Gestione Plugin'.")
            avviso.setStyleSheet(f"color: {TEMA['text_dim']};")
            layout.addWidget(avviso)

        layout.addStretch()
        self.instructions_screen.setWidget(content)

    def _build_logs_screen(self):
        self.logs_screen = QWidget()
        layout = QVBoxLayout(self.logs_screen)
        title = QLabel("Log di Sistema")
        title.setObjectName("section_title")
        layout.addWidget(title)

        self.logs_textbox = QTextEdit()
        self.logs_textbox.setReadOnly(True)
        self.logs_textbox.setStyleSheet("font-family: Consolas; font-size: 11px;")
        layout.addWidget(self.logs_textbox, 1)

    def _build_plugins_screen(self):
        self.plugins_screen = QScrollArea()
        self.plugins_screen.setWidgetResizable(True)
        self.plugins_screen.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)

        title = QLabel("Gestione Plugin")
        title.setObjectName("section_title")
        layout.addWidget(title)

        open_folder_btn = QPushButton("📁 Apri Cartella Plugin")
        open_folder_btn.setStyleSheet("background-color: #10b981; color: white; font-weight: bold; padding: 10px; border-radius: 5px;")
        open_folder_btn.setMaximumWidth(250)
        open_folder_btn.clicked.connect(self._open_plugins_folder)
        layout.addWidget(open_folder_btn)

        layout.addSpacing(10)

        from pathlib import Path
        plugins_dir = Path(__file__).parent / "plugins"

        self.plugin_checkboxes = {}
        disabled_plugins = self.config_data.get("disabled_plugins", [])

        plugins_card, pg_layout = self._create_card("🔌 Plugin Disponibili")

        from src.commands import _plugin_manager

        if _plugin_manager.all_plugins:
            for file_stem, plugin_inst in _plugin_manager.all_plugins.items():
                row_layout = QHBoxLayout()

                text_layout = QVBoxLayout()
                lbl_name = QLabel(f"{plugin_inst.name} ({file_stem}.py)")
                lbl_name.setStyleSheet("font-weight: bold; font-size: 14px;")

                lbl_desc = QLabel(plugin_inst.description)
                lbl_desc.setStyleSheet("color: #94a3b8; font-size: 11px;")
                lbl_desc.setWordWrap(True)

                text_layout.addWidget(lbl_name)
                text_layout.addWidget(lbl_desc)
                row_layout.addLayout(text_layout)

                cb = QCheckBox("Attivo")
                cb.setChecked(file_stem not in disabled_plugins)
                cb.stateChanged.connect(lambda state, name=file_stem, chbox=cb: chbox.setText("Attivo" if state else "Disabilitato"))
                self.plugin_checkboxes[file_stem] = cb
                row_layout.addWidget(cb)

                schema = plugin_inst.get_settings_schema()
                if schema:
                    set_btn = QPushButton("⚙️ Impostazioni")
                    set_btn.setFixedSize(130, 30)
                    set_btn.clicked.connect(lambda checked, p=plugin_inst: self._open_plugin_settings(p))
                    row_layout.addWidget(set_btn)
                else:
                    empty_lbl = QLabel("")
                    empty_lbl.setFixedSize(130, 30)
                    row_layout.addWidget(empty_lbl)

                pg_layout.addLayout(row_layout)

                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setStyleSheet("color: #334155;")
                pg_layout.addWidget(line)

        layout.addWidget(plugins_card)

        layout.addSpacing(20)
        save_btn = QPushButton("💾 Salva e Applica Plugin")
        save_btn.setFixedHeight(45)
        save_btn.setMaximumWidth(300)
        save_btn.setObjectName("save_btn")
        save_btn.clicked.connect(self.save_plugins_settings)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addStretch()
        self.plugins_screen.setWidget(content)

    def _build_history_screen(self):
        self.history_screen = QWidget()
        layout = QVBoxLayout(self.history_screen)
        title = QLabel("Cronologia Vecchia")
        title.setObjectName("section_title")
        layout.addWidget(title)

        self.history_textbox = QTextEdit()
        self.history_textbox.setReadOnly(True)
        layout.addWidget(self.history_textbox, 1)

    # =============== LOGIC ===============
    def toggle_sidebar(self):
        # QPropertyAnimation per width sidebar
        self.sidebar_anim = QPropertyAnimation(self.sidebar_frame, b"maximumWidth")
        self.sidebar_anim.setDuration(250)
        self.sidebar_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        if self.sidebar_collapsed:
            target_width = 220
            self._set_sidebar_text_mode(False)
        else:
            target_width = 70
            self._set_sidebar_text_mode(True)

        self.sidebar_anim.setStartValue(self.sidebar_frame.width())
        self.sidebar_anim.setEndValue(target_width)
        self.sidebar_anim.start()

        # Anche il minimumWidth deve seguire per forzare il layout
        self.sidebar_anim2 = QPropertyAnimation(self.sidebar_frame, b"minimumWidth")
        self.sidebar_anim2.setDuration(250)
        self.sidebar_anim2.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.sidebar_anim2.setStartValue(self.sidebar_frame.width())
        self.sidebar_anim2.setEndValue(target_width)
        self.sidebar_anim2.start()

        self.sidebar_collapsed = not self.sidebar_collapsed

    def _set_sidebar_text_mode(self, collapsed):
        if collapsed:
            self.logo_label.hide()
            for btn, text, name in self.nav_btns:
                btn.setText(text.split(" ")[0])
            self.mute_btn.setText("🔇")
            self.restart_btn.setText("🔄")
            self.status_label.hide()
        else:
            self.logo_label.show()
            for btn, text, name in self.nav_btns:
                btn.setText(text)
            self.mute_btn.setText("🎤 Disattiva Vocale" if not self.is_muted else "🔇 Attiva Vocale")
            self.restart_btn.setText("🔄 Riavvia OmniMind")
            self.status_label.show()

    def show_screen(self, screen_name):
        # Animate transition (Fade out / in)
        self.content_container.setCurrentWidget(self.screens[screen_name])
        for btn, text, name in self.nav_btns:
            btn.setChecked(name == screen_name)

        if screen_name == "history":
            self.load_history_items_gui()

        if screen_name == "dashboard":
            if not self.dashboard_timer.isActive():
                self._avvia_poll_wmi()
                self.dashboard_timer.start(2000)
                self._update_dashboard_stats()
        else:
            if hasattr(self, 'dashboard_timer') and self.dashboard_timer.isActive():
                self.dashboard_timer.stop()

    def _populate_settings_fields(self):
        self.key_entry.setText(self.config_data.get("gemini_api_key", ""))
        self.wakeword_entry.setText(self.config_data.get("wake_word", "omnimind"))
        self.voice_combo.setCurrentText(self.config_data.get("tts_voice", "it-IT-GiuseppeNeural"))
        self.tts_engine_combo.setCurrentText(self.config_data.get("tts_engine", "Microsoft Edge (Gratis)"))
        self.openai_key_entry.setText(self.config_data.get("openai_api_key", ""))
        self.openai_voice_combo.setCurrentText(self.config_data.get("openai_voice", "onyx"))
        self.model_combo.setCurrentText(self.config_data.get("gemini_model", "gemini-2.5-flash"))
        self.temp_slider.setValue(int(self.config_data.get("temperature", 0.7) * 10))
        self.mic_slider.setValue(int(self.config_data.get("mic_sensitivity", 400)))
        self.theme_combo.setCurrentText(self.config_data.get("theme", "Scuro"))
        self.accent_combo.setCurrentText(self.config_data.get("accent_color", "Azzurro"))
        self.windows_start_cb.setChecked(self.config_data.get("start_with_windows", False))
        self.minimize_start_cb.setChecked(self.config_data.get("start_minimized", False))
        self.rpa_delay_combo.setCurrentText(self.config_data.get("rpa_typing_delay", "Normale"))
        self.rpa_enter_cb.setChecked(self.config_data.get("rpa_auto_enter", True))
        self.spotify_id_entry.setText(self.config_data.get("spotify_client_id", ""))
        self.spotify_secret_entry.setText(self.config_data.get("spotify_client_secret", ""))
        self.eleven_key_entry.setText(self.config_data.get("elevenlabs_api_key", ""))
        self.eleven_voice_entry.setText(self.config_data.get("elevenlabs_voice_id", ""))
        self.safe_mode_cb.setChecked(self.config_data.get("safe_mode_confirm", False))
        self.log_combo.setCurrentText(self.config_data.get("log_level", "Info"))
        self.hotkey_entry.setText(self.config_data.get("hotkey_appunti", ""))

        # --- Profili / Modalità ---
        self.focus_mute_tts_check.setChecked(self.config_data.get("focus_mute_tts", True))
        self.focus_close_apps_check.setChecked(self.config_data.get("focus_close_apps", True))
        self.focus_block_notifications_check.setChecked(self.config_data.get("focus_block_notifications", False))

        gvol = float(self.config_data.get("gaming_volume", 0.30))
        self.gaming_volume_slider.setValue(int(gvol * 100))
        self.gaming_open_launchers_check.setChecked(self.config_data.get("gaming_open_launchers", True))
        self.gaming_optimize_ram_check.setChecked(self.config_data.get("gaming_optimize_ram", True))

        nvol = float(self.config_data.get("night_volume", 0.15))
        self.night_volume_slider.setValue(int(nvol * 100))
        self.night_bright_slider.setValue(int(self.config_data.get("night_brightness", 15)))

        avol = float(self.config_data.get("alarm_volume", 0.50))
        self.alarm_volume_slider.setValue(int(avol * 100))
        self.std_bright_slider.setValue(int(self.config_data.get("std_brightness", 80)))
        self.focus_pomodoro_check.setChecked(self.config_data.get("focus_pomodoro", False))
        self.focus_lofi_check.setChecked(self.config_data.get("focus_lofi", False))
        self.gaming_power_check.setChecked(self.config_data.get("gaming_high_performance", True))
        self.gaming_kill_browsers_check.setChecked(self.config_data.get("gaming_kill_browsers", False))
        self.night_blue_light_check.setChecked(self.config_data.get("night_blue_light", True))
        self.night_sleep_timer.setCurrentText(self.config_data.get("night_sleep_timer", "Mai"))
        self.trigger_time_night.setText(self.config_data.get("trigger_time_night", ""))
        self.trigger_app_gaming.setText(self.config_data.get("trigger_app_gaming", ""))

        # blockSignals: currentTextChanged e' collegato a on_profile_selected,
        # che esegue azioni di sistema reali (apre Steam, cambia volume e piano
        # energetico). Senza questo, il solo avvio dell'app le rieseguiva.
        self.profile_menu.blockSignals(True)
        active_prof = self.config_data.get("active_profile", "Nessuno")
        if active_prof == "Focus":
            self.profile_menu.setCurrentText("Focus / Studio")
        elif active_prof == "Gaming":
            self.profile_menu.setCurrentText("Gaming")
        elif active_prof == "Notte":
            self.profile_menu.setCurrentText("Notte / Relax")
        else:
            self.profile_menu.setCurrentText("Nessuno")
        self.profile_menu.blockSignals(False)

    def on_gaming_volume_slider_move(self, value):
        self.gaming_vol_pct_label.setText(f"{value}%")

    def save_settings(self):
        # Merge sullo stato su disco: riscrivere lo snapshot caricato all'avvio
        # cancellava le chiavi modificate nel frattempo da altre parti del
        # programma (es. il profilo attivato da un trigger automatico).
        self.config_data = load_config()
        self.config_data["gemini_api_key"] = self.key_entry.text().strip()
        self.config_data["wake_word"] = self.wakeword_entry.text().strip().lower()
        self.config_data["tts_voice"] = self.voice_combo.currentText()
        self.config_data["tts_engine"] = self.tts_engine_combo.currentText()
        self.config_data["openai_api_key"] = self.openai_key_entry.text().strip()
        self.config_data["openai_voice"] = self.openai_voice_combo.currentText()
        self.config_data["gemini_model"] = self.model_combo.currentText()
        self.config_data["temperature"] = self.temp_slider.value() / 10.0
        self.config_data["mic_sensitivity"] = self.mic_slider.value()
        self.config_data["theme"] = self.theme_combo.currentText()
        self.config_data["accent_color"] = self.accent_combo.currentText()
        self.config_data["start_with_windows"] = self.windows_start_cb.isChecked()
        self.config_data["start_minimized"] = self.minimize_start_cb.isChecked()
        self.config_data["rpa_typing_delay"] = self.rpa_delay_combo.currentText()
        self.config_data["rpa_auto_enter"] = self.rpa_enter_cb.isChecked()
        self.config_data["spotify_client_id"] = self.spotify_id_entry.text().strip()
        self.config_data["spotify_client_secret"] = self.spotify_secret_entry.text().strip()
        self.config_data["elevenlabs_api_key"] = self.eleven_key_entry.text().strip()
        self.config_data["elevenlabs_voice_id"] = self.eleven_voice_entry.text().strip()
        self.config_data["safe_mode_confirm"] = self.safe_mode_cb.isChecked()
        self.config_data["log_level"] = self.log_combo.currentText()
        self.config_data["hotkey_appunti"] = self.hotkey_entry.text().strip()

        save_config(self.config_data)
        if hasattr(self, 'on_settings_saved') and self.on_settings_saved:
            self.on_settings_saved(self.config_data)  # Passa il dizionario!

        self._toggle_windows_startup(self.windows_start_cb.isChecked())
        self._apply_theme()  # Applica istantaneamente il tema
        # I messaggi gia' in chat hanno i colori del tema precedente scritti
        # inline nell'HTML: vanno ridisegnati, altrimenti restano illeggibili.
        self._ridisegna_chat()
        self.show_notification("Impostazioni salvate con successo.")

    def save_profile_settings(self):
        self.config_data = load_config()
        self.config_data["focus_mute_tts"] = self.focus_mute_tts_check.isChecked()
        self.config_data["focus_close_apps"] = self.focus_close_apps_check.isChecked()
        self.config_data["focus_block_notifications"] = self.focus_block_notifications_check.isChecked()

        self.config_data["gaming_volume"] = self.gaming_volume_slider.value() / 100.0
        self.config_data["gaming_open_launchers"] = self.gaming_open_launchers_check.isChecked()
        self.config_data["gaming_optimize_ram"] = self.gaming_optimize_ram_check.isChecked()

        self.config_data["night_volume"] = self.night_volume_slider.value() / 100.0
        self.config_data["night_brightness"] = self.night_bright_slider.value()

        self.config_data["alarm_volume"] = self.alarm_volume_slider.value() / 100.0
        self.config_data["std_brightness"] = self.std_bright_slider.value()
        self.config_data["focus_pomodoro"] = self.focus_pomodoro_check.isChecked()
        self.config_data["focus_lofi"] = self.focus_lofi_check.isChecked()
        self.config_data["gaming_high_performance"] = self.gaming_power_check.isChecked()
        self.config_data["gaming_kill_browsers"] = self.gaming_kill_browsers_check.isChecked()
        self.config_data["night_blue_light"] = self.night_blue_light_check.isChecked()
        self.config_data["night_sleep_timer"] = self.night_sleep_timer.currentText()
        self.config_data["trigger_time_night"] = self.trigger_time_night.text().strip()
        self.config_data["trigger_app_gaming"] = self.trigger_app_gaming.text().strip()

        save_config(self.config_data)
        if hasattr(self, 'on_settings_saved') and self.on_settings_saved:
            self.on_settings_saved(self.config_data)

        self.show_notification("Configurazione Profili salvata con successo!")

    def on_profile_selected(self, selected_profile):
        from src.commands import attiva_profilo, disattiva_profili
        profili = {
            "Nessuno": None,
            "Focus / Studio": "focus",
            "Gaming": "gaming",
            "Notte / Relax": "notte",
        }
        if selected_profile not in profili:
            # Senza questa guardia, un testo non previsto lasciava `chat`
            # non inizializzata e la riga successiva sollevava UnboundLocalError.
            logger.warning(f"Profilo non riconosciuto dal menu: {selected_profile!r}")
            return

        nome = profili[selected_profile]
        success, chat, voice = disattiva_profili() if nome is None else attiva_profilo(nome)

        self.add_chat_log_entry("OmniMind", chat)
        self.config_data = load_config()
        self._populate_settings_fields()

    def check_queue(self):
        while not self.gui_queue.empty():
            try:
                msg_type, data = self.gui_queue.get_nowait()
                if msg_type == "status":
                    self.update_status(data)
                elif msg_type == "message":
                    sender, text = data
                    self.add_chat_log_entry(sender, text)
                elif msg_type == "system":
                    self.add_system_message(data)
                elif msg_type == "system_report":
                    formatted_data = data.replace('\n', '<br>').replace('  ', '&nbsp;&nbsp;')
                    self.chat_log.append(f"<span style='color:#64748b;'>{formatted_data}</span><br><br>")
                elif msg_type == "log":
                    level, log_msg = data
                    self.add_log_entry(level, log_msg)
                elif msg_type == "clear_input":
                    self.entry_box.clear()
                elif msg_type == "reload_config":
                    self.config_data = load_config()
                    self._populate_settings_fields()
                elif msg_type == "show_overlay":
                    text, duration = data
                    NotificationOverlay(self, text, duration)
                elif msg_type == "flash_screen":
                    ScreenFlashOverlay(self)
                elif msg_type == "show_image":
                    self.chat_log.append(f"<img src='{data}' width='250'><br>")
            except queue.Empty:
                break

    def toggle_mute(self):
        self.on_toggle_mute()

    def restart_app(self):
        # Spawna un nuovo processo indipendente clonato da questo
        subprocess.Popen([sys.executable] + sys.argv)
        # Uccide all'istante il processo attuale (compresi thread figli come PyAudio/Vosk)
        os._exit(0)

    def update_mute_ui(self, is_muted):
        self.is_muted = is_muted
        if self.sidebar_collapsed:
            self.mute_btn.setText("🔇" if is_muted else "🎤")
        else:
            if is_muted:
                self.mute_btn.setText("🔇 Attiva Vocale")
                self.mute_btn.setStyleSheet("background-color: #991b1b;")
            else:
                self.mute_btn.setText("🎤 Disattiva Vocale")
                self.mute_btn.setStyleSheet("background-color: #334155;")

    def update_status(self, state):
        self._current_state = state
        if self.on_state_change:
            self.on_state_change(state)
        state_config = {
            "listening": ("#10b981", "In ascolto..."),
            "recording": ("#ef4444", "Ascolto vocale..."),
            "processing": ("#f59e0b", "Elaborazione..."),
            "gemini_thinking": ("#f59e0b", "OmniMind pensa..."),
            "speaking": ("#a855f7", "OmniMind parla..."),
            "muted": ("#6b7280", "Disattivato."),
            "downloading": ("#06b6d4", "Download risorse...")
        }
        color, text = state_config.get(state, ("#95a5a6", "Stato sconosciuto"))
        self.status_circle.set_color(color)

        if not self.sidebar_collapsed:
            self.status_label.setText(text)

        if state == "listening":
            self._pulse_angle = 0.0
            if not self.pulse_timer.isActive():
                self.pulse_timer.start(30)
        else:
            self.pulse_timer.stop()
            self.status_circle.set_color(color)

        self._chat_status_dots_count = 0
        anim_states = ["listening", "recording", "processing", "gemini_thinking", "speaking", "downloading"]
        if state in anim_states:
            if not self.chat_status_timer.isActive():
                self.chat_status_timer.start(400)
        elif state == "muted":
            self.chat_status_timer.stop()
            self.chat_status_label.setText("In ascolto disattivato.")
        else:
            self.chat_status_timer.stop()
            self.chat_status_label.setText("")

    def _pulse_status_circle(self):
        self._pulse_angle += 0.12
        factor = (math.sin(self._pulse_angle) + 1.0) / 2.0
        self.status_circle.set_color(interpolate_color("#064e3b", "#34d399", factor))

    def _animate_chat_status(self):
        self._chat_status_dots_count = (self._chat_status_dots_count % 3) + 1
        dots = "." * self._chat_status_dots_count
        ww = self.config_data.get("wake_word", "omnimind")

        base = ""
        if self._current_state == "listening": base = f"In ascolto... di' '{ww}'"
        elif self._current_state == "recording": base = "Ti ascolto... parla ora"
        elif self._current_state == "processing": base = "Esecuzione comando"
        elif self._current_state == "gemini_thinking": base = "Elaborazione API Gemini"
        elif self._current_state == "speaking": base = "OmniMind sta parlando"
        elif self._current_state == "downloading": base = "Download in corso"

        self.chat_status_label.setText(f"{base}{dots}")

    def send_message(self):
        text = self.entry_box.text().strip()
        if text:
            self.entry_box.clear()
            self.add_chat_log_entry("Utente", text)
            self.on_send_text(text)

    def add_chat_log_entry(self, sender, text):
        # Sanitize HTML in user-supplied text to prevent injection
        import html
        safe_text = html.escape(text)
        if sender == "Utente":
            self.chat_log.append(
                f"<b style='color:{TEMA['utente']};'>Tu:</b> "
                f"<span style='color:{TEMA['text_main']};'>{safe_text}</span><br>")
        elif sender == "OmniMind":
            # Parsing del Markdown con estensioni per codice e tabelle
            md_html = markdown.markdown(text, extensions=['fenced_code', 'tables', 'nl2br'])

            # CSS basilare per stilizzare codice, citazioni e tabelle in dark mode
            styled_html = f"""
            <style>
                pre {{ background-color: {TEMA['card_bg']}; padding: 10px; border-radius: 5px; margin-top: 10px; margin-bottom: 10px; }}
                code {{ background-color: {TEMA['card_bg']}; padding: 2px 4px; border-radius: 3px; font-family: monospace; color: {TEMA['accent']}; }}
                table {{ border-collapse: collapse; margin: 10px 0; width: 100%; }}
                th, td {{ border: 1px solid #475569; padding: 5px; text-align: left; }}
            </style>
            <div style='color:{TEMA['text_main']}; font-family: Inter, sans-serif; margin-bottom:15px;'>
                <b style='color:{TEMA['assistente']};'>OmniMind:</b><br>
                {md_html}
            </div>
            """
            # Rendering istantaneo senza typewriter
            self.chat_log.append(styled_html)

            # Scorri automaticamente verso il basso
            self.chat_log.verticalScrollBar().setValue(self.chat_log.verticalScrollBar().maximum())
        else:
            # Per altri mittenti o messaggi di sistema classici
            self._typewriter_queue.append((sender, text))
            self._process_typewriter_queue()

    def _ridisegna_chat(self):
        """Ricostruisce la chat dal database con i colori del tema corrente."""
        try:
            from src.database import get_last_chat_messages
            self.chat_log.clear()
            for sender, msg in get_last_chat_messages(50):
                self.add_chat_log_entry(sender, msg)
        except Exception as e:
            logger.warning(f"Impossibile ridisegnare la chat dopo il cambio tema: {e}")

    def add_system_message(self, text):
        self._typewriter_queue.append(("[Sistema]", text))
        self._process_typewriter_queue()

    def _process_typewriter_queue(self):
        if self._processing_typewriter or not self._typewriter_queue:
            return
        self._processing_typewriter = True
        sender, text = self._typewriter_queue.pop(0)

        if sender == "[Sistema]":
            import html
            self.chat_log.append(f"<i style='color:#64748b;'>[Sistema] {html.escape(text)}</i><br>")
            self._processing_typewriter = False
            QTimer.singleShot(10, self._process_typewriter_queue)
        else:
            if sender == "OmniMind":
                self.chat_log.append("<b style='color:#10b981;'>OmniMind:</b> ")
            else:
                self.chat_log.append(f"<b style='color:#10b981;'>{sender}:</b> ")
            self._typewriter_insert(text + "\n", 0)

    def _typewriter_insert(self, text, char_index):
        if char_index < len(text):
            cursor = self.chat_log.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.chat_log.setTextCursor(cursor)

            char = text[char_index]
            if char == '\n':
                self.chat_log.insertHtml("<br>")
            else:
                self.chat_log.insertPlainText(char)

            self.chat_log.verticalScrollBar().setValue(self.chat_log.verticalScrollBar().maximum())
            QTimer.singleShot(15, lambda: self._typewriter_insert(text, char_index + 1))
        else:
            self.chat_log.insertHtml("<br>")
            self._processing_typewriter = False
            self._process_typewriter_queue()

    def add_log_entry(self, level, text):
        colors = {"INFO": "#10b981", "WARNING": "#f59e0b", "ERROR": "#ef4444", "CRITICAL": "#ef4444", "DEBUG": "#64748b"}
        color = colors.get(level, TEMA["text_main"])
        self.logs_textbox.append(f"<span style='color:{color};'>[{level}] {text}</span>")

    def load_history_items_gui(self):
        self.history_textbox.clear()
        import html
        from src.database import get_last_chat_messages
        history = get_last_chat_messages(100)
        for sender, msg in history:
            # QTextEdit.append interpreta la stringa come rich text: senza
            # escape un messaggio contenente <div> corrompeva la cronologia.
            msg = html.escape(msg)
            if sender == "Utente":
                self.history_textbox.append(
                    f"<b style='color:{TEMA['utente']};'>Tu:</b> "
                    f"<span style='color:{TEMA['text_main']};'>{msg}</span><br>")
            elif sender == "OmniMind":
                self.history_textbox.append(
                    f"<b style='color:{TEMA['assistente']};'>OmniMind:</b> "
                    f"<span style='color:{TEMA['text_main']};'>{msg}</span><br>")
            else:
                self.history_textbox.append(f"<i style='color:#64748b;'>[{sender}] {msg}</i><br>")

    def minimize_to_tray(self):
        self.hide()

    def restore_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def show_notification(self, text):
        NotificationOverlay(self, text, 3)

    def _toggle_windows_startup(self, enable):
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "OmniMind"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            if enable:
                script_path = os.path.abspath(sys.argv[0])
                # Su Windows, per lanciare pyw senza la console, assicurarsi di usare sys.executable
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, f'"{sys.executable}" "{script_path}"')
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            print(f"Errore Auto-Start: {e}")

    def clear_assistant_cache(self):
        from src.config import TEMP_DIR
        try:
            if TEMP_DIR.exists():
                shutil.rmtree(TEMP_DIR)
                TEMP_DIR.mkdir(parents=True, exist_ok=True)
            self.show_notification("Cache e Memoria temporanea svuotate con successo!")
        except Exception as e:
            self.show_notification(f"Errore durante lo svuotamento: {e}")

    def _open_plugins_folder(self):
        import os
        import subprocess
        from pathlib import Path
        plugins_dir = Path(__file__).parent / "plugins"
        plugins_dir.mkdir(exist_ok=True)
        if os.name == 'nt':
            subprocess.Popen(f'explorer "{plugins_dir}"')

    def save_plugins_settings(self):
        disabled = []
        for name, cb in self.plugin_checkboxes.items():
            if not cb.isChecked():
                disabled.append(name)

        # Merge sullo stato corrente su disco invece di riscrivere lo snapshot
        # caricato all'avvio: altrimenti questa schermata sovrascriveva anche
        # chiavi modificate nel frattempo da altre parti del programma.
        self.config_data = load_config()
        self.config_data["disabled_plugins"] = disabled
        save_config(self.config_data)

        from src.commands import _plugin_manager
        _plugin_manager.load_plugins()
        self.add_system_message("Impostazioni Plugin salvate. I plugin sono stati ricaricati.")

    def _open_plugin_settings(self, plugin_inst):
        """
        Dialogo delle impostazioni di un plugin.

        get_settings_schema() ritorna una LISTA di dizionari (vedi
        OmniMindPlugin): trattarla come un dizionario con .items() sollevava
        AttributeError e la finestra non si apriva mai.
        """
        schema = plugin_inst.get_settings_schema()
        if not schema:
            return

        from PyQt6.QtWidgets import QDialog, QFormLayout, QDialogButtonBox, QSpinBox

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Impostazioni: {plugin_inst.name}")
        dialog.setMinimumWidth(420)

        layout = QVBoxLayout(dialog)
        form = QFormLayout()

        correnti = plugin_inst.get_settings()
        campi = {}

        for voce in schema:
            chiave = voce["key"]
            etichetta = voce.get("label", chiave)
            tipo = voce.get("type", "str")
            valore = correnti.get(chiave, voce.get("default"))

            if tipo == "bool":
                widget = QCheckBox()
                widget.setChecked(bool(valore))
            elif tipo == "int":
                widget = QSpinBox()
                widget.setRange(int(voce.get("min", 0)), int(voce.get("max", 10000)))
                try:
                    widget.setValue(int(valore))
                except (TypeError, ValueError):
                    widget.setValue(0)
            else:
                widget = QLineEdit()
                widget.setText("" if valore is None else str(valore))

            campi[chiave] = (widget, tipo)
            form.addRow(f"{etichetta}:", widget)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        nuove = {}
        for chiave, (widget, tipo) in campi.items():
            if tipo == "bool":
                nuove[chiave] = widget.isChecked()
            elif tipo == "int":
                nuove[chiave] = widget.value()
            else:
                nuove[chiave] = widget.text().strip()

        # Delegato al plugin: usa settings_key() come chiave, la stessa che
        # get_settings() legge. La GUI scriveva invece sotto il nome del MODULO,
        # quindi il plugin non ritrovava mai i valori salvati.
        plugin_inst.save_settings(nuove)
        self.config_data = load_config()
        self.add_system_message(f"Impostazioni per {plugin_inst.name} salvate correttamente.")


class NotificationOverlay(QWidget):
    def __init__(self, parent, text, duration_sec=7):
        super().__init__()
        self.duration_sec = duration_sec
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # close() su un QWidget senza questo attributo si limita a nasconderlo:
        # ogni notifica restava in memoria per tutta la sessione.
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        layout = QVBoxLayout(self)
        frame = QFrame()
        frame.setStyleSheet("QFrame { background-color: rgba(30, 41, 59, 220); border: 2px solid #38bdf8; border-radius: 10px; }")
        fl = QVBoxLayout(frame)

        title = QLabel("🔔 OMNIMIND ALLERTA")
        title.setStyleSheet("color: #38bdf8; font-weight: bold; border: none; background: transparent;")
        fl.addWidget(title)

        msg = QLabel(text)
        msg.setStyleSheet("color: white; border: none; background: transparent;")
        fl.addWidget(msg)

        layout.addWidget(frame)

        self.resize(300, 130)
        # Posizione in basso a destra
        screen = parent.screen().geometry()
        self.move(screen.width() - 325, screen.height() - 190)

        self.setWindowOpacity(0.0)
        self.show()

        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(500)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(0.88)
        self.anim.start()

        QTimer.singleShot(duration_sec * 1000, self.fade_out)

    def fade_out(self):
        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(500)
        self.anim.setStartValue(self.windowOpacity())
        self.anim.setEndValue(0.0)
        self.anim.finished.connect(self.close)
        self.anim.start()

class ScreenFlashOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setStyleSheet("background-color: white;")
        self.setWindowOpacity(0.5)
        self.showFullScreen()

        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(300)
        self.anim.setStartValue(0.5)
        self.anim.setEndValue(0.0)
        self.anim.finished.connect(self.close)
        self.anim.start()

