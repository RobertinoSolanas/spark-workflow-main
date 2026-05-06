"""Prompts for the summarization workflow."""

# Instruction for handling image-only documents, to be reused in all prompts.
_IMAGE_ONLY_INSTRUCTION = (
    "**Sonderfall:** Wenn der zu verarbeitende Inhalt sehr kurz ist, hauptsächlich aus Bild-Platzhaltern wie `![...]` oder `<BILD>`-Tags besteht, "
    "oder eine Variation des Satzes 'Das Dokument besteht hauptsächlich aus einem oder mehreren visuellen Elementen' ist, "
    "soll deine Zusammenfassung ausschließlich der folgende Satz sein: 'Das Dokument besteht hauptsächlich aus einem oder mehreren visuellen Elementen. "
    "Eine detaillierte Beschreibung dieser Elemente ist nicht verfügbar.'\n\n"
)

# --- System prompts ---

INITIAL_SUMMARY_SYSTEM_PROMPT = (
    "Fasse den folgenden Inhalt auf Deutsch zusammen. Behalte alle wichtigen Informationen bei. "
    "Antworte detailliert und prägnant, ohne Einleitung oder unnötige Wiederholungen. "
    "Die Zusammenfassung sollte maximal 500 Wörter umfassen.\n\n"
    f"{_IMAGE_ONLY_INSTRUCTION}"
)

FINAL_OVERVIEW_SYSTEM_PROMPT = (
    "Bitte fasse die gegebenen Zusammenfassungen zu einer einzigen, deutschen, kohärenten Gesamtzusammenfassung zusammen. "
    "Behalte die wichtigsten Informationen bei. "
    "Antworte klar und prägnant, ohne Einleitung oder Wiederholungen. "
    "Die Zusammenfassung sollte maximal 800 Wörter umfassen.\n\n"
    f"{_IMAGE_ONLY_INSTRUCTION}"
)

FINAL_REFINEMENT_SYSTEM_PROMPT = (
    "Betone die wichtigsten Inhalte und Themen. "
    "Gib zu jedem Thema die wichtigen Details als ganze Sätze in Deutsch zurück. "
    "Antworte klar und strukturiert, ohne Einleitung oder unnötige Wiederholungen. "
    "Die finale Zusammenfassung sollte maximal 600 Wörter umfassen.\n\n"
    f"{_IMAGE_ONLY_INSTRUCTION}"
)

# --- User templates ---

INITIAL_SUMMARY_USER_TEMPLATE = "CONTENT:\n{external_data_tag_open}\n{content}\n{external_data_tag_close}"

FINAL_OVERVIEW_USER_TEMPLATE = (
    "Hier ist eine Sammlung von Zusammenfassungen:\n\n{external_data_tag_open}\n{complete_summary}\n{external_data_tag_close}"
)

FINAL_REFINEMENT_USER_TEMPLATE = (
    "Hier ist eine finale Zusammenfassung:\n\n{external_data_tag_open}\n{complete_summary}\n{external_data_tag_close}"
)
