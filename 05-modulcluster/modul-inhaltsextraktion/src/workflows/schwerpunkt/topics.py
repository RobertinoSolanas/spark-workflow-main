# src/workflows/metadata_extraction/chunk/topics.py
"""
Predefined list of topics for document chunk classification.
Each topic has a name and a description to aid in semantic matching.
"""

from typing import TypedDict


class Topic(TypedDict):
    name: str
    description: str
    id: int


TOPICS = [
    {
        "name": "Abfallwirtschaft / Kreislaufwirtschaft",
        "description": "Umgang mit Abfällen, Recycling und Kreislaufprozessen im Bau- und Planungsbereich.",
        "id": 1,
    },
    {
        "name": "Abschnittsbildung",
        "description": "Die Abschnittsbildung im Fachplanungsrecht bezeichnet die Möglichkeit, ein größeres Vorhaben in einzelne, eigenständige Teilabschnitte zu unterteilen und diese separat zu planen und festzustellen. Dies ist insbesondere dann zulässig, wenn eine Gesamtplanung aufgrund praktischer Schwierigkeiten nicht auf einmal realisiert werden kann. Die Planfeststellungsbehörde hat dabei ein planerisches Ermessen, das jedoch durch die Ziele des jeweiligen Fachplanungsgesetzes und das Abwägungsgebot begrenzt wird. Jeder Abschnitt muss für sich eine eigenständige Funktion erfüllen und darf nicht dazu führen, dass ungelöste Probleme („Planungstorso“) zurückbleiben. Die Abschnittsbildung dient auch dazu, mehrere Abschnitte zeitlich und inhaltlich parallel zu planen und so das Gesamtvorhaben zu beschleunigen. Dabei ist stets eine sachgerechte Abwägung zwischen den Vorteilen einer schnellen Umsetzung und möglichen Nachteilen erforderlich.",
        "id": 2,
    },
    {
        "name": "Alternativenprüfung / Variantenentscheidung",
        "description": "Die Alternativenprüfung im Planfeststellungsverfahren bezeichnet die Pflicht, verschiedene Standortalternativen für das geplante Vorhaben zu prüfen. Dabei wird analysiert, ob es andere Möglichkeiten gibt, das Ziel des Vorhabens zu erreichen, ohne dessen grundlegende Identität zu verändern. Eine Alternative wird nur so lange weiterverfolgt, bis deutlich wird, dass sie nicht eindeutig vorzugswürdig ist als die ursprüngliche Planung. Ziel ist es, sinnvolle und realistische Alternativen zu identifizieren, die das Projektziel nicht grundsätzlich infrage stellen. Bewertung und Auswahl zwischen verschiedenen Projekt- oder Trassenvarianten. Auch die Darstellung einer Vorzugstrasse, eines Trassenverlaufs, einer Trassenführung.",
        "id": 3,
    },
    {
        "name": "Altlasten",
        "description": "Erfassung und Behandlung von kontaminierten Flächen oder Bodenverunreinigungen.",
        "id": 4,
    },
    {
        "name": "Arbeitsschutz",
        "description": "Schutzmaßnahmen für Sicherheit und Gesundheit der Beschäftigten während Planung und Bau.",
        "id": 5,
    },
    {
        "name": "Artenschutz",
        "description": "Berücksichtigung geschützter Tier- und Pflanzenarten sowie ihrer Lebensräume.",
        "id": 6,
    },
    {
        "name": "Ausbaustandard / Technische Ausgestaltung",
        "description": "Festlegung technischer Standards und Bauweisen für das Projekt.",
        "id": 7,
    },
    {
        "name": "Ausgleichsmaßnahmen und Ersatzmaßnahmen",
        "description": "Ökologische Maßnahmen zum Ausgleich von Eingriffen in Natur und Landschaft.",
        "id": 8,
    },
    {
        "name": "Bergbau",
        "description": "Berührungspunkte mit aktiven oder stillgelegten Bergbauflächen und deren Sicherung.",
        "id": 9,
    },
    {
        "name": "Bodenschutz",
        "description": "Erhalt und Schutz der Bodenfunktionen vor schädlichen Veränderungen.",
        "id": 10,
    },
    {
        "name": "Brandschutz",
        "description": "Maßnahmen zur Vermeidung und Bekämpfung von Brandgefahren.",
        "id": 11,
    },
    {
        "name": "Denkmalschutz / Archäologie",
        "description": "Berücksichtigung von Kulturdenkmalen und archäologischen Funden.",
        "id": 12,
    },
    {
        "name": "Eingriffe in Natur und Landschaft",
        "description": "Bewertung und Minimierung der ökologischen Auswirkungen durch das Vorhaben.",
        "id": 13,
    },
    {
        "name": "Enteignungen und dingliche Sicherungen",
        "description": "Rechtliche Regelungen bei Grundstücksinanspruchnahmen und Sicherungsrechten.",
        "id": 14,
    },
    {
        "name": "Entschädigungsregelungen",
        "description": "Kompensation finanzieller Nachteile für Betroffene.",
        "id": 15,
    },
    {
        "name": "Fischerei",
        "description": "Auswirkungen des Projekts auf Fischbestände und Fischereiwirtschaft.",
        "id": 16,
    },
    {
        "name": "Forstwirtschaft",
        "description": "Beeinträchtigungen oder Anpassungen in bewirtschafteten Waldflächen.",
        "id": 17,
    },
    {
        "name": "Grundwasser",
        "description": "Einfluss auf Grundwasserstände, -qualität und -nutzung.",
        "id": 18,
    },
    {
        "name": "Hochwasserschutz",
        "description": "Berücksichtigung bestehender oder geplanter Hochwasserschutzmaßnahmen.",
        "id": 19,
    },
    {
        "name": "Immissionen, baubedingt – Lärm",
        "description": "Lärmbelastungen, die während der Bauphase entstehen.",
        "id": 20,
    },
    {
        "name": "Immissionen, baubedingt – Licht",
        "description": "Beeinträchtigungen durch künstliche Beleuchtung während der Bauarbeiten.",
        "id": 21,
    },
    {
        "name": "Immissionen, baubedingt – Staub",
        "description": "Staubentwicklung durch Erdarbeiten, Transporte und Bauprozesse.",
        "id": 22,
    },
    {
        "name": "Immissionen, baubedingt – Vibrationen",
        "description": "Erschütterungen und Schwingungen während der Bauausführung.",
        "id": 23,
    },
    {
        "name": "Immissionen, betriebsbedingt – Lärm",
        "description": "Dauerhafte Geräuschbelastung im Betrieb des Vorhabens.",
        "id": 24,
    },
    {
        "name": "Immissionen, betriebsbedingt – Licht",
        "description": "Lichtemissionen durch Anlagenbetrieb, Beleuchtung oder Infrastruktur.",
        "id": 25,
    },
    {
        "name": "Immissionen, betriebsbedingt – Staub",
        "description": "Staubentwicklung während des laufenden Betriebs.",
        "id": 26,
    },
    {
        "name": "Immissionen, betriebsbedingt – Vibrationen",
        "description": "Dauerhafte Vibrationen durch Nutzung oder Betrieb der Anlage.",
        "id": 27,
    },
    {
        "name": "Inanspruchnahme privater Flächen",
        "description": "Betroffenheit privater Grundstücke durch Bau oder Betrieb.",
        "id": 28,
    },
    {
        "name": "Kampfmittel",
        "description": "Gefahren und Funde von Munition oder Sprengstoffen aus früheren Konflikten.",
        "id": 29,
    },
    {
        "name": "Klimaschutz",
        "description": "Maßnahmen zur Reduktion von Treibhausgasemissionen und Klimafolgen.",
        "id": 30,
    },
    {
        "name": "Kreuzung mit bestehender Infrastruktur",
        "description": "Schnittstellen mit vorhandenen Straßen, Leitungen oder Bahntrassen.",
        "id": 31,
    },
    {
        "name": "Kreuzung mit Gewässern",
        "description": "Querungen von Flüssen, Bächen oder Kanälen und ihre Auswirkungen.",
        "id": 32,
    },
    {
        "name": "Landesplanung und Regionalplanung",
        "description": "Abgleich mit Zielen und Vorgaben der Raumordnung auf Landes- und Regionalebene.",
        "id": 33,
    },
    {
        "name": "Landwirtschaft",
        "description": "Nutzungskonflikte oder Beeinträchtigungen landwirtschaftlicher Flächen.",
        "id": 34,
    },
    {
        "name": "Natura 2000 - Verträglichkeit (FFH - / Vogelschutzgebiete)",
        "description": "Prüfung der Auswirkungen auf europäische Schutzgebiete und ihre Arten.",
        "id": 35,
    },
    {
        "name": "Oberflächengewässer",
        "description": "Beeinflussung von Flüssen, Seen und anderen Oberflächengewässern.",
        "id": 36,
    },
    {
        "name": "Öffentlicher Personennahverkehr",
        "description": "Anbindung und Auswirkungen auf Bus- und Bahnverbindungen.",
        "id": 37,
    },
    {
        "name": "Planrechtfertigung",
        "description": "Bei der Planrechtfertigung handelt es sich um eine Voraussetzung zur Beurteilung der Rechtmäßigkeit eines Vorhabens, das die Rechtsprechung aus der Bauleitplanung abgeleitet und auf das Fachplanungsrecht übertragen hat. Die Planrechtfertigung fordert, dass das Vorhaben, gemessen an den Zielen des jeweils zugrunde liegenden Fachgesetzes, objektiv vernünftigerweise geboten ist. Zur Begründung der Planrechtfertigung kann auch die Aufnahme eines Vorhabens in vorhandene Bedarfspläne herangezogen werden.",
        "id": 38,
    },
    {
        "name": "Raumordnung",
        "description": "Einhaltung von Vorgaben der übergeordneten räumlichen Planung.",
        "id": 39,
    },
    {
        "name": "Rettungswesen / Katastrophenschutz",
        "description": "Sicherstellung von Zugänglichkeit und Schutzmaßnahmen im Notfall.",
        "id": 40,
    },
    {
        "name": "Trinkwasserschutzgebiete",
        "description": "Besonderer Schutz von Arealen zur Trinkwassergewinnung.",
        "id": 41,
    },
    {
        "name": "Umweltverträglichkeitsprüfung – allgemein",
        "description": "Grundsätzliche Prüfung der Umweltauswirkungen des Projekts.",
        "id": 42,
    },
    {
        "name": "Umweltverträglichkeitsprüfung – Schutzgut Boden",
        "description": "Bewertung der Auswirkungen auf Bodenqualität und -funktionen.",
        "id": 43,
    },
    {
        "name": "Umweltverträglichkeitsprüfung – Schutzgut Fläche",
        "description": "Prüfung des Flächenverbrauchs und der Inanspruchnahme.",
        "id": 44,
    },
    {
        "name": "Umweltverträglichkeitsprüfung – Schutzgut Klima",
        "description": "Untersuchung der klimatischen Auswirkungen des Projekts.",
        "id": 45,
    },
    {
        "name": "Umweltverträglichkeitsprüfung – Schutzgut kulturelles Erbe und sonstige Sachgüter",
        "description": "Berücksichtigung materieller Kulturgüter und Sachwerte.",
        "id": 46,
    },
    {
        "name": "Umweltverträglichkeitsprüfung – Schutzgut Landschaft",
        "description": "Analyse der Eingriffe in Landschaftsbild und Erholungswert.",
        "id": 47,
    },
    {
        "name": "Umweltverträglichkeitsprüfung – Schutzgut Luft",
        "description": "Prüfung möglicher Luftschadstoffe oder Emissionen.",
        "id": 48,
    },
    {
        "name": "Umweltverträglichkeitsprüfung – Schutzgut Menschen, insbesondere die menschliche Gesundheit",
        "description": "Auswirkungen auf die Bevölkerung und ihre Gesundheit.",
        "id": 49,
    },
    {
        "name": "Umweltverträglichkeitsprüfung – Schutzgut Pflanzen, Tiere und die biologische Vielfalt",
        "description": "Analyse der Auswirkungen auf Flora, Fauna und Biodiversität.",
        "id": 50,
    },
    {
        "name": "Umweltverträglichkeitsprüfung – Schutzgut Wasser",
        "description": "Bewertung der Auswirkungen auf Grund- und Oberflächenwasser.",
        "id": 51,
    },
    {
        "name": "Umweltverträglichkeitsprüfung – Umfang und Methodik",
        "description": "Festlegung von Verfahren und Kriterien der UVP.",
        "id": 52,
    },
    {
        "name": "Umweltverträglichkeitsprüfung – Wechselwirkungen zwischen den Schutzgütern",
        "description": "Prüfung von Kombinationseffekten zwischen verschiedenen Schutzgütern.",
        "id": 53,
    },
    {
        "name": "Versorgungsanlagen und Entsorgungsanlagen / Leitungen",
        "description": "Planung und Berücksichtigung von Strom-, Wasser- und Abwasserleitungen.",
        "id": 54,
    },
    {
        "name": "Verkehr / Straßenbau",
        "description": "Auswirkungen auf Straßenbau, Verkehrswege und Mobilität.",
        "id": 55,
    },
    {
        "name": "Vermeidungsmaßnahmen und Minderungsmaßnahmen",
        "description": "Maßnahmen zur Vermeidung oder Verringerung von Umweltauswirkungen.",
        "id": 56,
    },
    {
        "name": "Vermessungswesen / Geoinformation",
        "description": "Erhebung und Nutzung von Geodaten für Planung und Bau.",
        "id": 57,
    },
    {
        "name": "Vorgezogene Ausgleichsmaßnahmen / CEF-Maßnahmen",
        "description": "Vorabmaßnahmen zum Schutz von Arten oder Lebensräumen.",
        "id": 58,
    },
    {
        "name": "Wasserrechtliche Erlaubnisse und Genehmigungen",
        "description": "Rechtliche Anforderungen im Umgang mit Wasserressourcen.",
        "id": 59,
    },
    {
        "name": "Wertminderungen von Grundstücken und Immobilien",
        "description": "Finanzielle Auswirkungen auf den Wert von Immobilien.",
        "id": 60,
    },
    {
        "name": "Zerschneidung der Landschaft",
        "description": "Trennwirkungen von Verkehrswegen oder Infrastrukturen in Landschaften.",
        "id": 61,
    },
    {
        "name": "Dokumentenverzeichnis",
        "description": 'Zum Beispiel ein Inhaltsverzeichnis eines Dokuments. Oder ein Abbildungsverzeichnis, Tabellenverzeichnis, Abkürzungsverzeichnis, Literaturverzeichnis etc. Erkennbar, wenn viele Überschriften mit (Seiten-)zahlen aufeinander folgen, wie zum Beispiel hier: "\n1.4 Beurteilung der Trassenalternativen 6   \n1.4.1 Ausschlusskriterien 6\n\n# 2 Betrachtete Varianten im Zuge der Machbarkeit und Vorplanung 7\n\n2.1 Großräumige Alternative 7 ".',
        "id": 62,
    },
    {
        "name": "Allgemeine Angaben zum Vorhaben / Kurzbeschreibung",
        "description": "Kurze zusammenfassende Darstellung des Vorhabens, seiner Ziele, wesentlichen Merkmale und des geplanten Ablaufs. Auch Angaben zum Vorhabenträger, der Antragsgegenstand oder zeitliche Angaben.",
        "id": 63,
    },
]
