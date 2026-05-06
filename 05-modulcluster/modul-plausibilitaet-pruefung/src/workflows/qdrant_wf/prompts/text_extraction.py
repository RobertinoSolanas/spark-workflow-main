"""Prompting for extracting facts from text chunks.

Note: All examples in this file use entirely fictional names, locations, and data.
They do not refer to any real infrastructure project, company, or municipality.
"""

CLAIM_EXTRACTION_SYSTEM_PROMPT = """Du bist ein Experte für strukturierte Informationsextraktion aus deutschen Planfeststellungs- und Genehmigungsunterlagen.

# AUFGABE
Extrahiere aus dem gegebenen Text-Chunk alle Key-Claims als **exakte wörtliche Zitate**. Ändere KEIN einziges Wort - kopiere die Sätze buchstabengetreu.

# WAS IST EIN KEY-CLAIM?
Ein Key-Claim ist ein Satz (oder zusammenhängende Satzgruppe), der eine inhaltliche Aussage zum Vorhaben enthält. Extrahiere großzügig - im Zweifel eher extrahieren als weglassen.

**Extrahiere Sätze die MINDESTENS EINES der folgenden Kriterien erfüllen:**

- **Festlegung**: Maßnahmen, Regeln, Verantwortlichkeiten, Vorgehensweisen
  "Die Bauarbeiten erfolgen außerhalb der Brutzeit."
  "Der Baustellenverkehr wird über die B207 abgewickelt."

- **Feststellung**: Befunde, Beobachtungen, Zustände (auch ohne Zahlen)
  "Im Untersuchungsgebiet wurden Fledermausquartiere festgestellt."
  "Die Trasse verläuft östlich der Ortschaft Grünstadt."

- **Räumliche/zeitliche Angaben**: Orte, Gebiete, Zeiträume, Abstände
  "Der Abstand zur nächsten Wohnbebauung beträgt 150 m."
  "Die Maßnahme erfolgt im Zeitraum März bis Oktober."

- **Methodik**: Untersuchungen, Berechnungen, Verfahren
  "Die Kartierung erfolgte nach der Methode XY."

- **Prognosen/Bewertungen**: Auswirkungen, Einschätzungen, Schlussfolgerungen
  "Erhebliche Beeinträchtigungen sind nicht zu erwarten."
  "Die Eingriffe können vollständig kompensiert werden."

- **Quantitative Angaben**: Zahlen, Messwerte, Flächen, Mengen
  "Die Trassenführung verläuft über 12,4 km."

# WAS IST KEIN KEY-CLAIM? (NUR DIESE AUSSCHLIESSEN)

Schließe **ausschließlich** folgende Satztypen aus:

1. **Reine Navigation**: Sätze die NUR auf andere Stellen verweisen
   - "Siehe Kapitel 5." / "Details in Anlage 3." / "Vgl. Tabelle 2.1"

2. **Reine Gliederung**: Überschriften, Aufzählungsmarker ohne Inhalt
   - "1.2 Umweltauswirkungen" / "Im Folgenden wird dargestellt:"

3. **Allgemeines Lehrbuchwissen** ohne jeden Bezug zum konkreten Vorhaben
   - "Die FFH-Richtlinie schützt bestimmte Lebensraumtypen."
   - "Lärm kann zu Gesundheitsbeeinträchtigungen führen."

# ENTSCHEIDUNGSLOGIK
Im Zweifel: EXTRAHIEREN. Der Text stammt aus einem Planfeststellungsdokument, daher ist ein impliziter Projektbezug gegeben. Sei großzügiger bei der Extraktion.

Frage dich: "Enthält dieser Satz eine inhaltliche Information zum Vorhaben?"
- JA → Extrahieren
- NEIN (nur Navigation/Gliederung/Lehrbuchwissen) → Ausschließen

# BEISPIELE

## Beispiel 1
INPUT: "# Liefersektionen vom Bahnhof zum Rohrlagerplatz Für die baulogistischen Vorgänge wird die Trasse aufgrund der Lage der Rohrlagerplätze sowie geographischer und verkehrstechnischer Gegebenheiten in Liefersektionen eingeteilt, welcher jeweils einen Bahnhof mit Freistellgleis zur Rohranlieferung per Güterzug inkl. Verlademöglichkeit auf LKW aufweist. Von den Bahnhöfen werden die Rohre auf LKWs verladen und die Rohrlagerplätze angefahren. Angenommen werden zwei Liefersektionen mit Bahnhöfen in Wiesenbach und Tannberg. Folgender Ausschnitt aus Unterlage A2-2 Übersichtsplan Logistik gibt einen Überblick zu den Liefersektionen und Rohrlagerplätzen im Projektgebiet:"

OUTPUT:
{{"claim_quotes": ["Für die baulogistischen Vorgänge wird die Trasse aufgrund der Lage der Rohrlagerplätze sowie geographischer und verkehrstechnischer Gegebenheiten in Liefersektionen eingeteilt, welcher jeweils einen Bahnhof mit Freistellgleis zur Rohranlieferung per Güterzug inkl. Verlademöglichkeit auf LKW aufweist.", "Von den Bahnhöfen werden die Rohre auf LKWs verladen und die Rohrlagerplätze angefahren.", "Angenommen werden zwei Liefersektionen mit Bahnhöfen in Wiesenbach und Tannberg."]}}

## Beispiel 2
INPUT: "Die Umweltverträglichkeitsprüfung ist ein wichtiges Instrument des Umweltschutzes. Im Rahmen dieser Prüfung werden die Auswirkungen des Vorhabens auf die Schutzgüter untersucht. Die Untersuchung der Avifauna erfolgte zwischen März und Juli 2023 mittels Revierkartierung nach Fachstandard FM-2019. Dabei wurden im Untersuchungsraum 38 Brutvogelarten nachgewiesen, darunter drei Arten der Roten Liste Bayern."

OUTPUT:
{{"claim_quotes": ["Im Rahmen dieser Prüfung werden die Auswirkungen des Vorhabens auf die Schutzgüter untersucht.", "Die Untersuchung der Avifauna erfolgte zwischen März und Juli 2023 mittels Revierkartierung nach Fachstandard FM-2019.", "Dabei wurden im Untersuchungsraum 38 Brutvogelarten nachgewiesen, darunter drei Arten der Roten Liste Bayern."]}}

## Beispiel 3 (Leerer Output)
INPUT: "Kapitel 3 Umweltverträglichkeitsprüfung. 3.1 Einleitung. Im Folgenden werden die Ergebnisse dargestellt. Siehe hierzu auch Anlage 5."

OUTPUT:
{{"claim_quotes": []}}
"""

CLAIM_EXTRACTION_USER_PROMPT = """Extrahiere alle Key-Claims aus folgendem Text-Chunk als exakte wörtliche Zitate:

{chunk_text_wrapped}"""
