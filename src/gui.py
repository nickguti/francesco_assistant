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
    QScrollArea, QStackedWidget, QGridLayout, QGroupBox
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRectF
from PyQt6.QtGui import QColor, QPainter, QTextCursor, QPen

from src.config import load_config, save_config

logger = logging.getLogger("OmniMindGUI")

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
        pen_bg = QPen(QColor("#1e293b"), 12)
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
        painter.setPen(QColor("white"))
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
    def __init__(self, gui_queue, on_send_text_callback, on_toggle_mute_callback, on_exit_callback, on_settings_saved_callback=None, on_stop_tts_callback=None, on_state_change_callback=None):
        super().__init__()
        self.gui_queue = gui_queue
        self.on_send_text = on_send_text_callback
        self.on_toggle_mute = on_toggle_mute_callback
        self.on_exit = on_exit_callback
        self.on_settings_saved = on_settings_saved_callback
        self.on_stop_tts = on_stop_tts_callback
        self.on_state_change = on_state_change_callback
        
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
            bg_sidebar = "#e2e8f0"
            bg_hover = "#cbd5e1"
            bg_input = "#ffffff"
            text_main = "#0f172a"
            text_dim = "#64748b"
            card_border = "#cbd5e1"
            card_bg = "#f1f5f9"
        else:
            bg_main = "#0f172a"
            bg_sidebar = "#1e293b"
            bg_hover = "#334155"
            bg_input = "#0b0f19"
            text_main = "#f8fafc"
            text_dim = "#94a3b8"
            card_border = "#334155"
            card_bg = "#1e293b"
            
        self.setStyleSheet(f"""
            QMainWindow, QWidget#content_container, QScrollArea, QScrollArea > QWidget > QWidget {{ background-color: {bg_main}; color: {text_main}; font-family: "Segoe UI"; }}
            QFrame#sidebar {{ background-color: {bg_sidebar}; border-right: 1px solid {bg_main}; }}
            QLabel {{ color: {text_main}; }}
            QLabel#logo_label {{ color: {accent}; font-size: 18px; font-weight: bold; }}
            QLabel#status_label {{ color: {text_dim}; font-size: 11px; }}
            QLabel#chat_status_label {{ color: {text_dim}; font-size: 11px; font-style: italic; }}
            QLabel#section_title {{ font-size: 20px; font-weight: bold; }}
            QPushButton {{ background-color: transparent; color: {text_main}; text-align: left; padding: 10px; border: none; font-weight: bold; font-size: 13px; border-radius: 5px; }}
            QPushButton:hover, QPushButton:checked {{ background-color: {bg_hover}; }}
            QPushButton#toggle_btn {{ font-size: 16px; padding: 5px; width: 30px; }}
            QPushButton#mute_btn {{ background-color: {bg_hover}; color: {text_main}; text-align: center; font-size: 11px; }}
            QPushButton#mute_btn:hover {{ background-color: {card_border}; }}
            QPushButton#send_btn, QPushButton#save_btn {{ background-color: {accent}; text-align: center; border-radius: 8px; color: #ffffff; }}
            QPushButton#send_btn:hover, QPushButton#save_btn:hover {{ opacity: 0.8; }}
            QPushButton#restart_btn {{ background-color: #7f1d1d; color: #f87171; border: 1px solid #991b1b; border-radius: 5px; margin-top: 5px; }}
            QPushButton#restart_btn:hover {{ background-color: #991b1b; color: white; }}
            QTextEdit, QLineEdit {{ background-color: {bg_input}; color: {text_main}; border: 1px solid {bg_hover}; border-radius: 8px; font-size: 13px; padding: 5px; }}
            QSlider::groove:horizontal {{ border: 1px solid {card_border}; height: 6px; background: {bg_main}; margin: 0px 0; border-radius: 3px; }}
            QSlider::handle:horizontal {{ background: {accent}; border: 1px solid {accent}; width: 14px; margin: -4px 0; border-radius: 7px; }}
            QComboBox {{ background-color: {bg_main}; border: 1px solid {card_border}; border-radius: 5px; padding: 5px; color: {text_main}; }}
            QComboBox::drop-down {{ border: none; }}
            QScrollBar:vertical {{ background: {bg_main}; width: 12px; margin: 0px 0px 0px 0px; }}
            QScrollBar::handle:vertical {{ background: {bg_hover}; min-height: 20px; border-radius: 6px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ border: none; background: none; }}
            QFrame#card {{ background-color: {card_bg}; border: 1px solid {card_border}; border-radius: 8px; }}
            QGroupBox {{ font-weight: bold; border: 1px solid {card_border}; border-radius: 6px; margin-top: 10px; padding-top: 15px; color: {text_main}; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 3px 0 3px; color: {accent}; }}
            QCheckBox {{ color: {text_main}; }}
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
        self._build_history_screen()

        # Add screens to stacked widget
        self.screens = {
            "chat": self.chat_screen,
            "settings": self.settings_screen,
            "modes": self.modes_screen,
            "instructions": self.instructions_screen,
            "logs": self.logs_screen,
            "dashboard": self.dashboard_screen,
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
        self.stop_tts_btn.clicked.connect(self._handle_stop_tts)
        
        input_layout.addWidget(self.entry_box, 1)
        input_layout.addWidget(self.stop_tts_btn)
        input_layout.addWidget(self.send_btn)
        layout.addLayout(input_layout)

    def _handle_stop_tts(self):
        if self.on_stop_tts:
            self.on_stop_tts()

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
        ai_group = QGroupBox("🧠 Intelligenza Artificiale")
        ai_layout = QGridLayout()
        ai_layout.addWidget(QLabel("Gemini API Key:"), 0, 0)
        self.key_entry = QLineEdit()
        self.key_entry.setEchoMode(QLineEdit.EchoMode.Password)
        ai_layout.addWidget(self.key_entry, 0, 1)
        
        ai_layout.addWidget(QLabel("Modello AI:"), 1, 0)
        self.model_combo = QComboBox()
        self.model_combo.addItems(["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-1.5-pro"])
        ai_layout.addWidget(self.model_combo, 1, 1)
        
        ai_layout.addWidget(QLabel("Creatività (Temp):"), 2, 0)
        self.temp_slider = QSlider(Qt.Orientation.Horizontal)
        self.temp_slider.setRange(0, 10)
        ai_layout.addWidget(self.temp_slider, 2, 1)
        ai_group.setLayout(ai_layout)
        grid.addWidget(ai_group, 0, 0)
        
        # --- Card 2: Hardware & Voce ---
        hw_group = QGroupBox("🎙️ Hardware & Voce")
        hw_layout = QGridLayout()
        hw_layout.addWidget(QLabel("Wake-Word:"), 0, 0)
        self.wakeword_entry = QLineEdit()
        hw_layout.addWidget(self.wakeword_entry, 0, 1)
        
        hw_layout.addWidget(QLabel("Sintesi Vocale:"), 1, 0)
        self.voice_combo = QComboBox()
        self.voice_combo.addItems(["it-IT-GiuseppeNeural", "it-IT-ElsaNeural", "it-IT-DiegoNeural"])
        hw_layout.addWidget(self.voice_combo, 1, 1)
        
        hw_layout.addWidget(QLabel("Soglia Rumore Mic:"), 2, 0)
        self.mic_slider = QSlider(Qt.Orientation.Horizontal)
        self.mic_slider.setRange(100, 2000)
        hw_layout.addWidget(self.mic_slider, 2, 1)
        hw_group.setLayout(hw_layout)
        grid.addWidget(hw_group, 0, 1)

        # --- Card 3: Aspetto & Sistema ---
        sys_group = QGroupBox("⚙️ Aspetto & Sistema")
        sys_layout = QGridLayout()
        sys_layout.addWidget(QLabel("Tema Scuro/Chiaro:"), 0, 0)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Scuro", "Chiaro"])
        sys_layout.addWidget(self.theme_combo, 0, 1)
        
        sys_layout.addWidget(QLabel("Colore Accento:"), 1, 0)
        self.accent_combo = QComboBox()
        self.accent_combo.addItems(["Azzurro", "Rosso", "Verde", "Viola", "Arancione"])
        sys_layout.addWidget(self.accent_combo, 1, 1)
        
        self.windows_start_cb = QCheckBox("Avvia automaticamente con Windows")
        sys_layout.addWidget(self.windows_start_cb, 2, 0, 1, 2)
        
        self.minimize_start_cb = QCheckBox("Avvia minimizzato nella Tray")
        sys_layout.addWidget(self.minimize_start_cb, 3, 0, 1, 2)
        sys_group.setLayout(sys_layout)
        grid.addWidget(sys_group, 1, 0)

        # --- Card 4: Automazione RPA ---
        rpa_group = QGroupBox("🤖 Automazione (RPA)")
        rpa_layout = QGridLayout()
        rpa_layout.addWidget(QLabel("Velocità Digitazione:"), 0, 0)
        self.rpa_delay_combo = QComboBox()
        self.rpa_delay_combo.addItems(["Lento (Sicuro)", "Normale", "Fulmineo"])
        rpa_layout.addWidget(self.rpa_delay_combo, 0, 1)
        
        self.rpa_enter_cb = QCheckBox("Premi 'Invio' in automatico dopo aver digitato")
        rpa_layout.addWidget(self.rpa_enter_cb, 1, 0, 1, 2)
        rpa_group.setLayout(rpa_layout)
        grid.addWidget(rpa_group, 1, 1)

        # --- Card 5: Integrazioni API ---
        api_group = QGroupBox("🌐 Integrazioni e Servizi Esterni")
        api_layout = QGridLayout()
        api_layout.addWidget(QLabel("Spotify Client ID:"), 0, 0)
        self.spotify_id_entry = QLineEdit()
        self.spotify_id_entry.setEchoMode(QLineEdit.EchoMode.Password)
        api_layout.addWidget(self.spotify_id_entry, 0, 1)
        
        api_layout.addWidget(QLabel("Spotify Secret:"), 0, 2)
        self.spotify_secret_entry = QLineEdit()
        self.spotify_secret_entry.setEchoMode(QLineEdit.EchoMode.Password)
        api_layout.addWidget(self.spotify_secret_entry, 0, 3)
        
        api_layout.addWidget(QLabel("ElevenLabs API Key:"), 1, 0)
        self.eleven_key_entry = QLineEdit()
        self.eleven_key_entry.setEchoMode(QLineEdit.EchoMode.Password)
        api_layout.addWidget(self.eleven_key_entry, 1, 1)
        
        api_layout.addWidget(QLabel("ElevenLabs Voice ID:"), 1, 2)
        self.eleven_voice_entry = QLineEdit()
        api_layout.addWidget(self.eleven_voice_entry, 1, 3)
        api_group.setLayout(api_layout)
        grid.addWidget(api_group, 2, 0, 1, 2)

        # --- Card 6: Sicurezza & Dati ---
        sec_group = QGroupBox("🛡️ Sicurezza & Gestione Dati")
        sec_layout = QGridLayout()
        
        self.safe_mode_cb = QCheckBox("Safe Mode: Chiedi conferma vocale prima di eseguire comandi irreversibili")
        sec_layout.addWidget(self.safe_mode_cb, 0, 0, 1, 3)
        
        sec_layout.addWidget(QLabel("Livello di Log:"), 1, 0)
        self.log_combo = QComboBox()
        self.log_combo.addItems(["Debug", "Info", "Error"])
        sec_layout.addWidget(self.log_combo, 1, 1)
        
        self.clear_cache_btn = QPushButton("🗑️ Svuota Cache e Memoria")
        self.clear_cache_btn.setStyleSheet("background-color: #ef4444; color: white; border: none; font-weight: bold; border-radius: 5px;")
        self.clear_cache_btn.clicked.connect(self.clear_assistant_cache)
        sec_layout.addWidget(self.clear_cache_btn, 1, 2)
        
        sec_group.setLayout(sec_layout)
        grid.addWidget(sec_group, 3, 0, 1, 2)
        
        layout.addLayout(grid)
        layout.addSpacing(20)
        
        save_btn = QPushButton("💾 Salva Configurazioni")
        save_btn.setFixedHeight(45)
        save_btn.setStyleSheet("background-color: #38bdf8; color: #0f172a; font-weight: bold; border-radius: 5px;")
        save_btn.clicked.connect(self.save_settings)
        layout.addWidget(save_btn)
        
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
        active_group = QGroupBox("🌟 Profilo di Sistema Attivo")
        active_layout = QGridLayout()
        active_layout.addWidget(QLabel("Seleziona Profilo (applica subito):"), 0, 0)
        self.profile_menu = QComboBox()
        self.profile_menu.addItems(["Nessuno", "Focus / Studio", "Gaming", "Notte / Relax"])
        self.profile_menu.currentTextChanged.connect(self.on_profile_selected)
        active_layout.addWidget(self.profile_menu, 0, 1)
        active_group.setLayout(active_layout)
        layout.addWidget(active_group)
        
        grid = QGridLayout()
        grid.setSpacing(20)
        
        # --- Card 2: Focus / Studio ---
        focus_group = QGroupBox("📚 Profilo Focus / Studio")
        focus_layout = QVBoxLayout()
        self.focus_mute_tts_check = QCheckBox("Silenzia risposte vocali (TTS)")
        self.focus_close_apps_check = QCheckBox("Termina app distrattive all'avvio")
        self.focus_block_notifications_check = QCheckBox("Silenzia notifiche desktop")
        self.focus_pomodoro_check = QCheckBox("Avvia Timer Pomodoro (25min)")
        self.focus_lofi_check = QCheckBox("Riproduci Playlist Lo-Fi (Spotify)")
        focus_layout.addWidget(self.focus_mute_tts_check)
        focus_layout.addWidget(self.focus_close_apps_check)
        focus_layout.addWidget(self.focus_block_notifications_check)
        focus_layout.addWidget(self.focus_pomodoro_check)
        focus_layout.addWidget(self.focus_lofi_check)
        focus_group.setLayout(focus_layout)
        grid.addWidget(focus_group, 0, 0)
        
        # --- Card 3: Gaming ---
        gaming_group = QGroupBox("🎮 Profilo Gaming")
        gaming_layout = QVBoxLayout()
        gv_layout = QHBoxLayout()
        gv_layout.addWidget(QLabel("Volume in gioco:"))
        self.gaming_volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.gaming_volume_slider.setRange(0, 100)
        self.gaming_vol_pct_label = QLabel("30%")
        self.gaming_vol_pct_label.setFixedWidth(40)
        gv_layout.addWidget(self.gaming_volume_slider)
        gv_layout.addWidget(self.gaming_vol_pct_label)
        gaming_layout.addLayout(gv_layout)
        
        self.gaming_open_launchers_check = QCheckBox("Avvia automaticamente launcher")
        self.gaming_optimize_ram_check = QCheckBox("Ottimizza RAM liberando cache")
        self.gaming_power_check = QCheckBox("Attiva Piano Prestazioni Eccellenti")
        self.gaming_kill_browsers_check = QCheckBox("Forza chiusura browser pesanti")
        gaming_layout.addWidget(self.gaming_open_launchers_check)
        gaming_layout.addWidget(self.gaming_optimize_ram_check)
        gaming_layout.addWidget(self.gaming_power_check)
        gaming_layout.addWidget(self.gaming_kill_browsers_check)
        gaming_group.setLayout(gaming_layout)
        grid.addWidget(gaming_group, 0, 1)
        
        # --- Card 4: Notte / Relax ---
        night_group = QGroupBox("🌙 Profilo Notte / Relax")
        night_layout = QVBoxLayout()
        nv_layout = QHBoxLayout()
        nv_layout.addWidget(QLabel("Volume Notturno:"))
        self.night_volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.night_volume_slider.setRange(0, 100)
        self.night_vol_pct_label = QLabel("15%")
        self.night_vol_pct_label.setFixedWidth(40)
        nv_layout.addWidget(self.night_volume_slider)
        nv_layout.addWidget(self.night_vol_pct_label)
        night_layout.addLayout(nv_layout)
        
        nb_layout = QHBoxLayout()
        nb_layout.addWidget(QLabel("Luminosità Schermo:"))
        self.night_bright_slider = QSlider(Qt.Orientation.Horizontal)
        self.night_bright_slider.setRange(0, 100)
        self.night_bright_pct_label = QLabel("15%")
        self.night_bright_pct_label.setFixedWidth(40)
        nb_layout.addWidget(self.night_bright_slider)
        nb_layout.addWidget(self.night_bright_pct_label)
        night_layout.addLayout(nb_layout)
        
        self.night_blue_light_check = QCheckBox("Attiva Filtro Luce Blu (Windows)")
        night_layout.addWidget(self.night_blue_light_check)
        
        sl_layout = QHBoxLayout()
        sl_layout.addWidget(QLabel("Timer Auto-Spegnimento:"))
        self.night_sleep_timer = QComboBox()
        self.night_sleep_timer.addItems(["Mai", "30 min", "1 ora", "2 ore"])
        sl_layout.addWidget(self.night_sleep_timer)
        night_layout.addLayout(sl_layout)
        
        night_group.setLayout(night_layout)
        grid.addWidget(night_group, 1, 0)
        
        # --- Card 5: Standard / Quotidiano ---
        std_group = QGroupBox("☀️ Profilo Standard / Sveglia")
        std_layout = QVBoxLayout()
        av_layout = QHBoxLayout()
        av_layout.addWidget(QLabel("Volume Sveglia:"))
        self.alarm_volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.alarm_volume_slider.setRange(0, 100)
        self.alarm_vol_pct_label = QLabel("50%")
        self.alarm_vol_pct_label.setFixedWidth(40)
        av_layout.addWidget(self.alarm_volume_slider)
        av_layout.addWidget(self.alarm_vol_pct_label)
        std_layout.addLayout(av_layout)
        
        sb_layout = QHBoxLayout()
        sb_layout.addWidget(QLabel("Luminosità Standard:"))
        self.std_bright_slider = QSlider(Qt.Orientation.Horizontal)
        self.std_bright_slider.setRange(0, 100)
        self.std_bright_pct_label = QLabel("80%")
        self.std_bright_pct_label.setFixedWidth(40)
        sb_layout.addWidget(self.std_bright_slider)
        sb_layout.addWidget(self.std_bright_pct_label)
        std_layout.addLayout(sb_layout)
        std_group.setLayout(std_layout)
        grid.addWidget(std_group, 1, 1)
        
        # --- Card 6: Trigger Automatici ---
        trigger_group = QGroupBox("⚡ Trigger di Auto-Attivazione")
        trigger_layout = QGridLayout()
        trigger_layout.addWidget(QLabel("Attiva 'Notte' alle ore:"), 0, 0)
        self.trigger_time_night = QLineEdit()
        self.trigger_time_night.setPlaceholderText("Es. 23:00")
        trigger_layout.addWidget(self.trigger_time_night, 0, 1)
        
        trigger_layout.addWidget(QLabel("Attiva 'Gaming' se apro l'app:"), 1, 0)
        self.trigger_app_gaming = QLineEdit()
        self.trigger_app_gaming.setPlaceholderText("Es. steam.exe")
        trigger_layout.addWidget(self.trigger_app_gaming, 1, 1)
        trigger_group.setLayout(trigger_layout)
        grid.addWidget(trigger_group, 2, 0, 1, 2)
        
        layout.addLayout(grid)
        layout.addSpacing(20)
        
        save_btn = QPushButton("💾 Salva Configurazioni Profili")
        save_btn.setFixedHeight(45)
        save_btn.setObjectName("save_btn")
        save_btn.clicked.connect(self.save_profile_settings)
        layout.addWidget(save_btn)
        
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
        
        self._wmi_poll_running = True
        
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
                
        threading.Thread(target=poll_wmi_cpu, daemon=True).start()
        
        self.dashboard_screen.setWidget(content)
        
        self.dashboard_timer = QTimer(self)
        self.dashboard_timer.timeout.connect(self._update_dashboard_stats)

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
                capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
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
        self.instructions_screen = QScrollArea()
        self.instructions_screen.setWidgetResizable(True)
        self.instructions_screen.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        
        title = QLabel("Manuale dei Comandi")
        title.setObjectName("section_title")
        layout.addWidget(title)
        layout.addWidget(QLabel("Interagisci vocalmente dicendo 'OmniMind [comando]' o scrivendo nella chat:"))
        
        commands_list = [
            {"title": "💬 Chiacchierata Generica", "synonyms": "Ciao OmniMind / Cerca su internet...", "desc": "Conversazione libera basata sul Cloud. Usa Gemini per rispondere."},
            {"title": "🎭 Cambio Profilo", "synonyms": "cambia profilo in [nome]", "desc": "Passa dal profilo Nessuno, a Focus o Gaming alterando il comportamento."},
            {"title": "🔇 Controllo Audio", "synonyms": "muto / smuta / pausa / riprendi", "desc": "Gestisce la riproduzione multimediale in background e le allerte sonore."},
            {"title": "⏰ Sveglie e Timer", "synonyms": "imposta un timer di X minuti", "desc": "Avvia un timer con allarme acustico in background."},
            {"title": "📋 Analizzatore Appunti", "synonyms": "spiegami gli appunti", "desc": "Legge il testo copiato nel tuo clipboard di Windows e lo analizza."},
            {"title": "📄 Lettore Documenti", "synonyms": "riassumi il file / leggi il documento", "desc": "Estrae il testo da file locali (.txt, .pdf) e ne genera un riassunto."},
            {"title": "👁️ [NUOVO] Visione Schermo 2.0", "synonyms": "guarda qui / analizza lo schermo", "desc": "Scatta un flash fotografico multi-monitor e analizza cosa stai guardando."},
            {"title": "🤖 [NUOVO] Automazioni RPA", "synonyms": "esegui automazione: [azione]", "desc": "L'IA prende il controllo di tastiera e finestre per eseguire task per te."},
            {"title": "📊 [NUOVO] Monitor PC & Killer", "synonyms": "come sta il PC? / chiudi [app]", "desc": "Legge le temperature GPU, CPU e RAM in tempo reale o termina app forzatamente."}
        ]
        
        for cmd in commands_list:
            c = QFrame()
            c.setObjectName("card")
            cl = QVBoxLayout(c)
            tl = QLabel(cmd["title"])
            tl.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 14px;")
            cl.addWidget(tl)
            cl.addWidget(QLabel(f"Es: \"{cmd['synonyms']}\""))
            dl = QLabel(cmd["desc"])
            dl.setWordWrap(True)
            dl.setStyleSheet("color: #94a3b8;")
            cl.addWidget(dl)
            layout.addWidget(c)
            
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
                self.dashboard_timer.start(2000)
                self._update_dashboard_stats()
        else:
            if hasattr(self, 'dashboard_timer') and self.dashboard_timer.isActive():
                self.dashboard_timer.stop()

    def _populate_settings_fields(self):
        self.key_entry.setText(self.config_data.get("gemini_api_key", ""))
        self.wakeword_entry.setText(self.config_data.get("wake_word", "omnimind"))
        self.voice_combo.setCurrentText(self.config_data.get("tts_voice", "it-IT-GiuseppeNeural"))
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
        
        active_prof = self.config_data.get("active_profile", "Nessuno")
        if active_prof == "Focus":
            self.profile_menu.setCurrentText("Focus / Studio")
        elif active_prof == "Gaming":
            self.profile_menu.setCurrentText("Gaming")
        elif active_prof == "Notte":
            self.profile_menu.setCurrentText("Notte / Relax")
        else:
            self.profile_menu.setCurrentText("Nessuno")

    def on_volume_slider_move(self, value):
        self.vol_percent_label.setText(f"{value}%")

    def on_alarm_volume_slider_move(self, value):
        self.alarm_vol_percent_label.setText(f"{value}%")

    def on_gaming_volume_slider_move(self, value):
        self.gaming_vol_pct_label.setText(f"{value}%")

    def on_tts_rate_slider_move(self, value):
        self.tts_rate_value_label.setText(f"{value:+d}%")

    def on_tts_pitch_slider_move(self, value):
        self.tts_pitch_value_label.setText(f"{value:+d}Hz")

    def save_settings(self):
        self.config_data["gemini_api_key"] = self.key_entry.text().strip()
        self.config_data["wake_word"] = self.wakeword_entry.text().strip().lower()
        self.config_data["tts_voice"] = self.voice_combo.currentText()
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
        
        save_config(self.config_data)
        if hasattr(self, 'on_settings_saved') and self.on_settings_saved:
            self.on_settings_saved(self.config_data)  # Passa il dizionario!
            
        self._toggle_windows_startup(self.windows_start_cb.isChecked())
        self._apply_theme()  # Applica istantaneamente il tema
        self.show_notification("Impostazioni salvate con successo.")

    def save_profile_settings(self):
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
        if selected_profile == "Nessuno":
            success, chat, voice = disattiva_profili()
        elif selected_profile == "Focus / Studio":
            success, chat, voice = attiva_profilo("focus")
        elif selected_profile == "Gaming":
            success, chat, voice = attiva_profilo("gaming")
        elif selected_profile == "Notte / Relax":
            success, chat, voice = attiva_profilo("notte")
            
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
            self.chat_log.append(f"<b style='color:#60a5fa;'>Tu:</b> <span style='color:#f8fafc;'>{safe_text}</span><br>")
        elif sender == "OmniMind":
            # Parsing del Markdown con estensioni per codice e tabelle
            md_html = markdown.markdown(text, extensions=['fenced_code', 'tables', 'nl2br'])
            
            # CSS basilare per stilizzare codice, citazioni e tabelle in dark mode
            styled_html = f"""
            <style>
                pre {{ background-color: #1e293b; padding: 10px; border-radius: 5px; margin-top: 10px; margin-bottom: 10px; }}
                code {{ background-color: #1e293b; padding: 2px 4px; border-radius: 3px; font-family: monospace; color: #38bdf8; }}
                table {{ border-collapse: collapse; margin: 10px 0; width: 100%; }}
                th, td {{ border: 1px solid #475569; padding: 5px; text-align: left; }}
            </style>
            <div style='color:#f8fafc; font-family: Inter, sans-serif; margin-bottom:15px;'>
                <b style='color:#10b981;'>OmniMind:</b><br>
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

    def add_system_message(self, text):
        self._typewriter_queue.append(("[Sistema]", text))
        self._process_typewriter_queue()

    def _process_typewriter_queue(self):
        if self._processing_typewriter or not self._typewriter_queue:
            return
        self._processing_typewriter = True
        sender, text = self._typewriter_queue.pop(0)
        
        if sender == "[Sistema]":
            self.chat_log.append(f"<i style='color:#64748b;'>[Sistema] {text}</i><br>")
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
        color = colors.get(level, "#f8fafc")
        self.logs_textbox.append(f"<span style='color:{color};'>[{level}] {text}</span>")

    def load_history_items_gui(self):
        self.history_textbox.clear()
        from src.database import get_last_chat_messages
        history = get_last_chat_messages(100)
        for sender, msg in history:
            if sender == "Utente":
                self.history_textbox.append(f"<b style='color:#60a5fa;'>Tu:</b> <span style='color:#f8fafc;'>{msg}</span><br>")
            elif sender == "OmniMind":
                self.history_textbox.append(f"<b style='color:#10b981;'>OmniMind:</b> <span style='color:#f8fafc;'>{msg}</span><br>")
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

class NotificationOverlay(QWidget):
    def __init__(self, parent, text, duration_sec=7):
        super().__init__()
        self.duration_sec = duration_sec
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
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
        self.setStyleSheet("background-color: white;")
        self.setWindowOpacity(0.5)
        self.showFullScreen()
        
        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(300)
        self.anim.setStartValue(0.5)
        self.anim.setEndValue(0.0)
        self.anim.finished.connect(self.close)
        self.anim.start()

