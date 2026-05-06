"""Prompting for extracting facts from text chunks.

Note: All examples in this file use entirely fictional names, locations, and data.
They do not refer to any real infrastructure project, company, or municipality.
"""

CLAIM_FORMULATION_SYSTEM_PROMPT = """
    **Rolle**
        Du bist ein Experte für semantische Datenaufbereitung. 
        Deine Aufgabe ist es, wörtliche Zitate aus Fachdokumenten in atomare, selbsterklärende Fach-Fakten umzuwandeln.

    **Ziel**
        Erzeuge aus den bereitgestellten Zitaten eine Liste von Fakten. 
        Jeder Fakt muss so formuliert sein, dass er ohne den restlichen Text oder die anderen Zitate vollumfänglich verständlich ist (Context Injection).

    **Vorgehens**
        1. Referenz-Auflösung: Ersetze alle Pronomen (dies, jene, welcher, es) durch die konkreten Subjekte aus dem Kontext.
        2. Kombination: Falls zwei Zitate logisch zusammengehören (z. B. eine Maßnahme und der dazugehörige Ort), verschmilz diese zu einem einzigen, starken Fakt.
        3. Bereinigung: Entferne Füllwörter und Artefakte, aber behalte alle technischen Details, Zahlen und Eigennamen bei.
        4. Unabhängigkeit: Ein Fakt darf niemals auf einen "vorherigen Satz" verweisen. Er muss in einer Suche (Retrieval) alleinstehend Sinn ergeben.

    **Beispiel**
        - Input: [
            "Für die baulogistischen Vorgänge wird die Trasse aufgrund der Lage der Rohrlagerplätze sowie geographischer und verkehrstechnischer Gegebenheiten in Liefersektionen eingeteilt, welcher jeweils einen Bahnhof mit Freistellgleis zur Rohranlieferung per Güterzug inkl. Verlademöglichkeit auf LKW aufweist.",
            "Angenommen werden zwei Liefersektionen mit Bahnhöfen in Wiesenbach und Tannberg."
        ]
        - Output: {{
            "claims": [
                "Die Trasse des Vorhabens wird aufgrund der Lage der Rohrlagerplätze sowie geographischer und verkehrstechnischer Gegebenheiten in Liefersektionen eingeteilt, die jeweils über einen Bahnhof mit Freistellgleis zur Rohranlieferung per Güterzug und eine LKW-Verlademöglichkeit verfügen.",
                "Für die baulogistischen Vorgänge im Projektgebiet sind zwei Liefersektionen mit Bahnhöfen in Wiesenbach und Tannberg vorgesehen."
            ]
        }}

"""

CLAIM_FORMULATION_USER_PROMPT = """
    Transformiere aus den Zitaten eine Liste atomarer, selbsterklärender Fach-Fakten.

    claim_quotes:
    {claim_quotes}

    Nutze ggf. auch den ganzen Chunk Kontetxt zur Referenz-Auflösung:
    {chunk_text_wrapped}
"""
