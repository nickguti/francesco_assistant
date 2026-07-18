class OmniMindPlugin:
    """Classe base per tutti i plugin di OmniMind."""
    
    def can_handle(self, text_clean: str, text: str) -> bool:
        """
        Restituisce True se il plugin è in grado di gestire questo comando.
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
