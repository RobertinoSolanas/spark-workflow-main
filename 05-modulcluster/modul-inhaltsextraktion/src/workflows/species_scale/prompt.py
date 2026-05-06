# src/workflows/species_scale/prompt.py
"""Prompts for the Species/Scale extraction workflow."""

_SPECIES_AND_SCALE_RULES = """
Regeln:
- `wildlife_mentioned`: Setze dies auf `true`, wenn eine oder mehrere Wildtierarten explizit namentlich genannt werden (z.B. "Feldhase", "Rotmilan"). Setze es auf `false`, wenn nur allgemein von "Tieren" oder "Fauna" die Rede ist.
- `plant_species_mentioned`: Setze dies auf `true`, wenn eine oder mehrere Pflanzenarten explizit namentlich genannt werden (z.B. "Stieleiche", "Winterlinde"). Setze es auf `false`, wenn nur allgemein von "Pflanzen" oder "Flora" die Rede ist.
- `wildlife_species`: Liste die exakten Namen aller erwähnten Wildtierarten auf.
- `plant_species`: Liste die exakten Namen aller erwähnten Pflanzenarten auf.
- `map_scale`: Gib den Maßstab an, falls einer erwähnt wird (z.B. "1:250", "1:1000"). Wenn keiner erwähnt wird, setze den Wert auf `null`.
"""

SPECIES_SCALE_SYSTEM_PROMPT = (
    """Analysiere den folgenden Textabschnitt und extrahiere die angeforderten Informationen.
Antworte ausschließlich im JSON-Format.
"""
    + _SPECIES_AND_SCALE_RULES
)

SPECIES_SCALE_USER_TEMPLATE = """Textabschnitt:
{external_data_tag_open}
{markdown_content}
{external_data_tag_close}
"""

BATCHED_SPECIES_SCALE_SYSTEM_PROMPT = (
    """Analysiere die folgenden nummerierten Textabschnitte und extrahiere für JEDEN Abschnitt die angeforderten Informationen.
"""
    + _SPECIES_AND_SCALE_RULES
    + """
WICHTIG:
- Du MUSST für JEDEN Textabschnitt genau eine Extraktion zurückgeben.
- Die Reihenfolge der Ergebnisse MUSS exakt der Reihenfolge der Eingabe-Textabschnitte entsprechen.
- Die Anzahl der Extraktionen MUSS exakt der Anzahl der Textabschnitte entsprechen.

Deine Ausgabe MUSS ein einzelnes, sauberes JSON-Objekt sein. Füge keinerlei Markdown-Formatierung, einleitenden Text oder Erklärungen außerhalb der JSON-Struktur hinzu. Format:

{{
  "extractions": [
    {{
      "wildlife_mentioned": <true|false>,
      "plant_species_mentioned": <true|false>,
      "wildlife_species": ["Art1", "Art2"],
      "plant_species": ["Art1", "Art2"],
      "map_scale": "<Maßstab oder null>"
    }},
    ...
  ]
}}"""
)

BATCHED_SPECIES_SCALE_USER_TEMPLATE = """{external_data_tag_open}
{chunks_text}
{external_data_tag_close}

Antwort:
"""
