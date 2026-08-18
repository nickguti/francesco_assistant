from src.config import get_setting, save_config, load_config


class OmniMindPlugin:
    """Classe base per tutti i plugin di OmniMind."""

    name = "Plugin Sconosciuto"
    description = "Nessuna descrizione disponibile."

    # Ordine di interrogazione nel dispatcher: valore piu' basso = interrogato prima.
    # I plugin con trigger specifici devono precedere quelli con trigger generici
    # (es. AppsLauncher, che cattura qualunque frase che inizi con "apri").
    priority = 50

    # Esempi mostrati nella guida comandi della GUI: (frase, descrizione).
    examples: list[tuple[str, str]] = []

    def get_settings_schema(self) -> list[dict]:
        """
        Ritorna lo schema delle impostazioni del plugin.
        Formato atteso (lista di dizionari):
        [
            {"key": "chiave_impostazione", "label": "Etichetta UI", "type": "str|bool|int", "default": "valore"}
        ]
        """
        return []

    def get_settings(self) -> dict:
        """Legge le impostazioni correnti di questo plugin dal config.json."""
        all_plugin_settings = get_setting("plugin_settings", {})
        my_settings = all_plugin_settings.get(self.settings_key(), {})

        # Merge con i default dello schema
        schema = self.get_settings_schema()
        merged = {}
        for item in schema:
            key = item["key"]
            merged[key] = my_settings.get(key, item.get("default"))
        return merged

    @classmethod
    def settings_key(cls) -> str:
        """
        Chiave usata in config.json['plugin_settings'].
        Unica fonte di verita': GUI e plugin devono usare entrambi questo metodo,
        altrimenti la GUI scrive in un nodo che il plugin non legge mai.
        """
        return cls.__name__

    def save_settings(self, new_settings: dict):
        """Salva le nuove impostazioni nel config.json sotto la chiave del plugin."""
        config_data = load_config()
        if "plugin_settings" not in config_data:
            config_data["plugin_settings"] = {}

        config_data["plugin_settings"][self.settings_key()] = new_settings
        save_config(config_data)
        self.apply_settings(new_settings)

    def apply_settings(self, new_settings: dict):
        """
        Hook opzionale: invocato dopo il salvataggio per applicare le impostazioni
        a runtime. I plugin senza stato interno non devono sovrascriverlo.
        """
        return

    def can_handle(self, text_clean: str, text: str) -> bool:
        """
        Restituisce True se il plugin e' in grado di gestire questo comando.
        :param text_clean: Il testo formattato (lower e strip).
        :param text: Il testo originale.
        """
        raise NotImplementedError

    def execute(self, text_clean: str, text: str) -> tuple[bool, str, str]:
        """
        Esegue il comando.
        :param text_clean: Il testo formattato.
        :param text: Il testo originale.
        :return: (is_command, chat_response, voice_response).
        """
        raise NotImplementedError
