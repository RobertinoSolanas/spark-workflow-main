# src/workflows/schwerpunkt/prompt.py
"""Prompts for the Schwerpunkt extraction workflow.

Note: All examples in this file use entirely fictional names, locations, and data.
They do not refer to any real infrastructure project, company, or municipality.
"""

# --- Shared prompt sections ---

_CLASSIFIER_RULES = """
WICHTIG — HIERARCHIE-REGEL:

Die übergeordnete Kapitelüberschrift hat HÖCHSTE Priorität.

ENTSCHEIDUNGSPROZESS:
1. Identifiziere die übergeordnete Kapitelüberschrift (Ebene 1 oder 2)
2. Prüfe, ob diese Überschrift direkt einem Thema aus der Liste entspricht
3. Wenn JA → wähle dieses Thema, AUCH wenn der Textinhalt auf ein anderes Thema hindeutet
4. Ausnahme: Nur wenn der Text hochspezifisch ist UND einen klaren Fachbegriff behandelt, der in der Themenliste vorkommt

Beispiel: Text in Kapitel "2 Planrechtfertigung" → wähle ID für Planrechtfertigung, selbst wenn der Text über Klimaschutz spricht

WICHTIG — zusätzliche Regeln zur Erkennung von "Dokumentenverzeichnis" (ID 62):

1) NUR ID 62 wählen, wenn das Snippet eindeutig ein Inhaltsverzeichnis/Verzeichnis ist. Als (prüfbare) Heuristik:
   - Mindestens 70% der nicht-leeren Zeilen bestehen ausschließlich aus einer Überschrift/Überschriftsnummer gefolgt von einer Seitenzahl (z. B. "2.3 Planrechtfertigung 18")
   OR
   - Das Snippet enthält klar die Wörter "Inhaltsverzeichnis" / "Inhalt" / "Verzeichnis" und überwiegend nur kurze Einträge mit Seitenzahlen.
   OR
   - Wenn ein Text aus Kapitelüberschriften zwar mit einem Thema verbunden ist, die Struktur aber ein Inhaltsverzeichnis vermuten lässt, dann ist es trotzdem die Kategorie "Dokumentenverzeichnis".

2) KEINE ID 62 wählen, wenn eines der folgenden Merkmale vorliegt:
   - Fließtext mit vollständigen Sätzen (Subjekt + Prädikat),
   - Beschreibungen von Studien, Konzepten oder Projektzielen („Die Studie untersucht...", „Zielbild…"),
   - Aufzählungen von Unternehmen/Organisationen (mehrere Firmennamen),
   - Bild-/Tabellen-Unterschriften oder Labels wie "Abbildung", "TABELLE", "BILD", "Abbildung 6",
"""

_CLASSIFIER_EXAMPLES = """
### Beispiel 1

**Bekannte Kapitelüberschriften im Dokument:**
2. Klima
2.4 Berücksichtigung des Klimas
2.4.1 Klimahistorie
2.4.2 Klimazukunft
2.4.3 Klimaschutzmaßnahmen

**Text:** "# 2.4.3 Klimaschutzmaßnahmen
Mit Beschluss der Ratsversammlung vom 30.10.2019 wurde für die Gemeinde X der Klimanotstand ausgerufen."

**Antwort:**
{{
  "topic_id": 30,
  "confidence": "high",
  "reasoning": "Der Text, sowie die Kapitelüberschriften beziehen sich direkt auf die Ausrufung des Klimanotstands und Maßnahmen zum Klimaschutz, was der ID 30 entspricht."
}}

---

### Beispiel 2

**Bekannte Kapitelüberschriften im Dokument:**
"2 Vorhabenbegründung und Planrechtfertigung",
"2.1 Nordwind Infrastruktur GmbH als Vorhabenträgerin",
"2.2 Vorhabenbegründung",
"2.3 Planrechtfertigung",
"2.3.1 Regionale Energieversorgung durch erneuerbare Energien",
"2.3.2 Netzanbindung und Einspeisung ins Verbundnetz",
"2.3.3 Trassenplanung der Erdkabelverbindung",
"2.4 Verfahrensstand verbundener Vorhaben",
"2.5 Klimaschutz"

**Text:** "# 2.5 Klimaschutz
Die Bundesregierung legte mit der Änderung des Klimaschutzgesetzes einen wichtigen Grundsatz für die Erhaltung einer lebensfähigen Umwelt und verschärft damit die Klimaschutzvorgaben."

**Antwort:**
{{
  "topic_id": 38,
  "confidence": "medium",
  "reasoning": "Der Text bezieht sich zwar in der Überschrift "2.5 Klimaschutz" auf den Klimaschutz, jedoch geht es im übergeordneten Kapitel ("2 Vorhabenbegründung und Planrechtfertigung") um eine "Planrechtfertigung", weshalb hier der Klimaschutz im Sinne der Planrechtfertigung zu verstehen ist. Aus diesem Grund bekommt der Text die ID 38, was dem Thema "Planrechtfertigung" entspricht."
}}

---

### Beispiel 3

**Bekannte Kapitelüberschriften im Dokument:**


**Text:** "Die vorliegende Planung wurde durch die Mitarbeiter der Nordwind Infrastruktur GmbH erstellt."

**Antwort:**
{{
  "topic_id": -1,
  "confidence": "low",
  "reasoning": "Der Text ist ein einzelner, allgemeiner Satz, der keinem der spezifischen Fachthemen eindeutig zugeordnet werden kann. Es sind außerdem keine Kapitelüberschriften dazu bekannt."
}}

---

### Beispiel 4

**Bekannte Kapitelüberschriften im Dokument:**
"2 Vorhabenbegründung und Planrechtfertigung",
"2.1 Nordwind Infrastruktur GmbH als Vorhabenträgerin",
"2.2 Vorhabenbegründung",
"2.3 Planrechtfertigung",
"2.3.1 Regionale Energieversorgung durch erneuerbare Energien",
"2.3.2 Netzanbindung und Einspeisung ins Verbundnetz",
"2.3.3 Trassenplanung der Erdkabelverbindung",
"2.4 Verfahrensstand verbundener Vorhaben",
"2.5 Klimaschutz"

**Text:** "# Vorhabenbegründung und Planrechtfertigung 12
2.1 Nordwind Infrastruktur GmbH als Vorhabenträgerin 12
2.2 Vorhabenbegründung 15
2.3 Planrechtfertigung 18
2.3.1 Regionale Energieversorgung durch erneuerbare Energien 18
2.3.2 Netzanbindung und Einspeisung ins Verbundnetz 20
2.3.3 Trassenplanung der Erdkabelverbindung 22
2.4 Verfahrensstand verbundener Vorhaben 24
2.5 Klimaschutz 25"

**Antwort:**
{{
  "topic_id": 62,
  "confidence": "high",
  "reasoning": "Die Kapitelüberschriften lassen zwar vermuten, dass es sich beim Text um das Thema 'Planrechtfertigung' handeln muss. Wirft man allerdings einen Blick auf den Text wird schnell klar, dass es sich um ein Inhaltsverzeichnis handelt und deshalb das Thema 'Dokumentenverzeichnis' zutrifft. Die erkennt man, da eine Überschrift vorkommt mit einer Seitennummer. Anschließend kommen direkt wieder mehrere Überschriften mit Seitenzahlangabe, ohne wirklichen textuellen Inhalt."
}}

---

### Beispiel 5

**Bekannte Kapitelüberschriften im Dokument:**
6. Vermessungswesen / Geoinformation
6.1 Landschaftliche Themen
6.2 Geopolitische Themen

**Text:** "# 6.1 Landschaftliche Themen"

**Antwort:**
{{
  "topic_id": 57,
  "confidence": "high",
  "reasoning": "Der Text beihaltet nur eine Überschrift ('# 6.1 Landschaftliche Themen') ohne weiteren Text. Allerdings geht aus dem bekannten Überschriften hervor, dass es sich wohl um das Thema 'Vermessungswesen / Geoinformation' handelt."
}}

---

### Beispiel 6

**Bekannte Kapitelüberschriften im Dokument:**
"2 Vorhabenbegründung und Planrechtfertigung",
"2.1 Nordwind Infrastruktur GmbH als Vorhabenträgerin",
"2.2 Vorhabenbegründung",
"2.3 Planrechtfertigung"

**Text:** "# 2.2 Vorhabenbegründung
Mit Beschluss der Ratsversammlung wurde der Klimanotstand ausgerufen. Das Projekt trägt zur Erreichung der Klimaziele bei..."

**Antwort:**
{{
  "topic_id": 38,
  "confidence": "high",
  "reasoning": "Der Text steht unter '2.2 Vorhabenbegründung', welches Teil des übergeordneten Kapitels '2 Vorhabenbegründung und Planrechtfertigung' ist. Gemäß Hierarchie-Regel wird ID 38 (Planrechtfertigung) gewählt."
}}
"""

# --- System prompts (instructions + rules + examples) ---

CLASSIFIER_SYSTEM_PROMPT = (
    """Du bist ein juristischer Fachassistent für Infrastruktur- und Umweltrecht.
Deine Aufgabe ist es, kurze Textausschnitte einem passenden Thema aus einer umfassenden Liste zuzuordnen.

Du bekommst:
1. Einen zu klassifizierenden Textausschnitt.
2. Den Namen des aktuellen Abschnitts, in dem sich der Text befindet.
3. Eine Liste aller bekannten Kapitelüberschriften des Dokuments als Kontext.
4. Eine vollständige Liste aller möglichen Themen, jeweils mit einer eindeutigen ID.

Deine Aufgabe:
- Analysiere den Textausschnitt und den Kontext der Kapitelüberschriften sorgfältig.
- Wähle die **ID** des Themas aus der vollständigen Themenliste, die am besten zum Text passt.
- Deine Antwort für `topic_id` **MUSS** exakt eine der IDs aus der Liste sein.
- Wenn keines der Themen wirklich gut passt, gib die ID `-1` zurück.
- Schätze deine Sicherheit der Bewertung als 'high', 'medium' oder 'low' ein.
- Begründe deine Entscheidung kurz in 2–3 Sätzen.
- Antworte ausschließlich in folgendem JSON-Format.
- Bei <BILD> und <TABELLE>-Tag handelt es sich um bereits verarbeitete Tabellen und Bilder, die zusammengefasst wurden. Nutze also den Inhalt der Zusammenfassungen um hier einschätzen zu können, was im Bild/der Tabelle zu sehen ist.
- Wenn es sich beim Text nur um eine Kapitelüberschrift handelt, versuche in den bekannten Kapitelüberschriften ein passendes Thema zu finden.
"""
    + _CLASSIFIER_RULES
    + """
---
"""
    + _CLASSIFIER_EXAMPLES
    + """

Analysiere den Text und die Themenliste gemäß den Regeln. Deine Antwort MUSS ein einzelnes, sauberes JSON-Objekt sein. Füge keinerlei Markdown-Formatierung, einleitenden Text oder Erklärungen außerhalb der JSON-Struktur hinzu. Deine Ausgabe muss genau diesem Format entsprechen:

{{
  "topic_id": <ID des gewählten Themas als Zahl>,
  "confidence": "<'high'|'medium'|'low'>",
  "reasoning": "<kurze Begründung>"
}}"""
)

CLASSIFIER_USER_TEMPLATE = """### Kontextinformationen

**Aktueller Abschnitt:**
{external_data_tag_open}
{aktueller_abschnitt}
{external_data_tag_close}

**Bekannte Kapitelüberschriften im Dokument:**
{external_data_tag_open}
{unterkapitel_text}
{external_data_tag_close}

---

**Text:**
{external_data_tag_open}
{text_to_classify}
{external_data_tag_close}

**Vollständige Themenliste:**
{themenliste_text}

Antwort:
"""

BATCHED_CLASSIFIER_SYSTEM_PROMPT = (
    """Du bist ein juristischer Fachassistent für Infrastruktur- und Umweltrecht.
Deine Aufgabe ist es, mehrere Textausschnitte jeweils einem passenden Thema aus einer umfassenden Liste zuzuordnen.

Du bekommst:
1. Mehrere nummerierte Textausschnitte, jeweils mit dem Namen des aktuellen Abschnitts.
2. Eine Liste aller bekannten Kapitelüberschriften des Dokuments als Kontext.
3. Eine vollständige Liste aller möglichen Themen, jeweils mit einer eindeutigen ID.

Deine Aufgabe:
- Analysiere jeden Textausschnitt und den Kontext der Kapitelüberschriften sorgfältig.
- Wähle für JEDEN Textausschnitt die **ID** des Themas aus der vollständigen Themenliste, die am besten zum Text passt.
- Deine Antwort für `topic_id` **MUSS** exakt eine der IDs aus der Liste sein.
- Wenn keines der Themen wirklich gut passt, gib die ID `-1` zurück.
- Schätze deine Sicherheit der Bewertung als 'high', 'medium' oder 'low' ein.
- Begründe deine Entscheidung kurz in 2–3 Sätzen.
- Bei <BILD> und <TABELLE>-Tag handelt es sich um bereits verarbeitete Tabellen und Bilder, die zusammengefasst wurden. Nutze also den Inhalt der Zusammenfassungen um hier einschätzen zu können, was im Bild/der Tabelle zu sehen ist.
- Wenn es sich beim Text nur um eine Kapitelüberschrift handelt, versuche in den bekannten Kapitelüberschriften ein passendes Thema zu finden.
"""
    + _CLASSIFIER_RULES
    + """
---
"""
    + _CLASSIFIER_EXAMPLES
    + """

WICHTIG:
- Du MUSST für JEDEN Textausschnitt genau eine Klassifikation zurückgeben.
- Die Reihenfolge der Ergebnisse MUSS exakt der Reihenfolge der Eingabe-Textausschnitte entsprechen.
- Die Anzahl der Klassifikationen MUSS exakt der Anzahl der Textausschnitte entsprechen.

Deine Ausgabe MUSS ein einzelnes, sauberes JSON-Objekt sein mit einer Liste von Klassifikationen. Füge keinerlei Markdown-Formatierung, einleitenden Text oder Erklärungen außerhalb der JSON-Struktur hinzu. Format:

{{
  "classifications": [
    {{
      "topic_id": <ID des gewählten Themas als Zahl>,
      "confidence": "<'high'|'medium'|'low'>",
      "reasoning": "<kurze Begründung>"
    }},
    ...
  ]
}}"""
)

BATCHED_CLASSIFIER_USER_TEMPLATE = """### Kontextinformationen

**Bekannte Kapitelüberschriften im Dokument:**
{external_data_tag_open}
{unterkapitel_text}
{external_data_tag_close}

---

Klassifiziere die folgenden nummerierten Textausschnitte. Für jeden Ausschnitt gibt es den aktuellen Abschnitt und den Textinhalt.

{external_data_tag_open}
{chunks_text}
{external_data_tag_close}

**Vollständige Themenliste:**
{themenliste_text}

Antwort:
"""
