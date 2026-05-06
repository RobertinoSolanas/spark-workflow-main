from typing import Literal, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

T = TypeVar("T")

NormTyp = Literal["materiell-rechtlich", "verfahrensrechtlich"]

SatzKategorie = Literal["wenn-dann", "abwägungsdirektive", "begriffserklärung", "sonstiges"]

Sollensanordnungen = Literal["verbot", "gebot", "erlaubnis", "freistellung"]

RechtsfolgenAdressat = Literal[
    "handlungsermächtigung",
    "keine handlungsermächtigung",
]

Ermessensspielraum = Literal["ermessensentscheidung", "gebundene entscheidung"]


ErmessensArt = Literal[
    "entschließungsermessen",
    "auswahlermessen",
    "beides",
]


class Absatz[T](BaseModel):
    absatz_nr: str
    absatz_text: str
    saetze: list[T]


class TechnischeNorm(BaseModel):
    id: str
    kurzbeschreibung: str


class Auslegungsvorschlag(BaseModel):
    auslegung_methode: str
    auslegungsvorschlag: str
    sources: list[str] | None = None


class UnbestimmterRechtsbegriff(BaseModel):
    begriff: str
    auslegungsvorschläge: list[Auslegungsvorschlag]
    auslegung: str | None = None


class Source(BaseModel):
    jurabk: str
    paragraph_nr: str


class Legaldefinition(BaseModel):
    begriff: str
    definition: str
    source: Source


class BestimmterRechtsbegriff(BaseModel):
    begriff: str
    definitions: list[Legaldefinition]
    selected_definition: Legaldefinition | None = None


class Rechtsbegriffe(BaseModel):
    unbestimmte_rechtsbegriffe: list[UnbestimmterRechtsbegriff]
    bestimmte_rechtsbegriffe: list[BestimmterRechtsbegriff]


class Untergliederung(BaseModel):
    typ: str
    wert: str


class ExplicitVerweiseInfo(BaseModel):
    gesetz: str | None = None
    paragraph_nr: str | None = None
    absatz_nr: str | None = None
    satz_nr: str | None = None
    untergliederung: list[Untergliederung] | None = None
    anhang: str | None = None
    artikel: str | None = None
    richtlinie: str | None = None
    verordnung: str | None = None
    technische_norm: TechnischeNorm | None = None
    verweis_typ: Literal["intern", "extern"] | None
    kontext: list[str] | None = None


class Verweise(BaseModel):
    explizit: list[ExplicitVerweiseInfo]
    implizit: list[str]


class AtomaresTBM(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    text: str
    verweise: Verweise
    prueffrage: str
    pruefgegenstand: str
    rechtsbegriffe: Rechtsbegriffe


class Rechtsfolge(BaseModel):
    text: str
    sollensanordnungen: Sollensanordnungen
    rechtsfolgen_adressat: RechtsfolgenAdressat
    ermessensspielraum: Ermessensspielraum | None = None
    ermessensart: ErmessensArt | None = None
    verweise: Verweise | None = None


class NormDekonstruktionInput(BaseModel):
    jurabk: str
    paragraph_nr: str


class NormDekonstruktionSatzOutput(BaseModel):
    satz_nr: str
    markers: list[str]
    satz_text: str
    norm_typ_lvl_1: NormTyp
    norm_typ_lvl_2: SatzKategorie | None = None
    tatbestandsmerkmale: list[str] | None = None
    rechtsfolge: Rechtsfolge | None = None
    wenn_dann_satz: str | None = None
    atomare_tatbestandsmerkmale: list[AtomaresTBM] | None = None
    formel: str | None = None


class NormDekonstruktionOutput(BaseModel):
    gesetz: str
    jurabk: str
    standangaben: list[dict]
    paragraph_nr: str
    paragraph_titel: str
    paragraph_text: str
    absaetze: list[Absatz[NormDekonstruktionSatzOutput]]
    regelungsgegenstand: str | None


class LMAtomareTBMsWorkflowInput(BaseModel):
    gesetz: str = Field(..., description="The law")
    jurabk: str = Field(..., description="Abbreviation of the law")
    paragraph_nr: str = Field(..., description="Paragraph number")
    paragraph_text: str = Field(..., description="Text of the paragraph")
    absatz_nr: str = Field(..., description="Number of the section (Absatz)")
    satz_nr: str = Field(..., description="Sentence number within the section")
    markers: list[str] = Field(..., description="List of markers for subdivision of a sentence")
    satz_text: str = Field(..., description="Text of the sentence")
    ex_atomare_tatbestandsmerkmale: list[str] = Field(..., description="Existing atomare TBMs")
    new_atomare_tatbestandsmerkmale: list[str] = Field(..., description="Added or edited atomare TBMs")
    rechtsfolge: str = Field(..., description="Legal consequence")


class LMAtomareTBMsWorkflowOutput(BaseModel):
    atomare_tatbestandsmerkmale: list[AtomaresTBM] | None = None
    formel: str | None = None


class LMJuristischerSatzWorkflowInput(BaseModel):
    gesetz: str = Field(..., description="The law")
    jurabk: str = Field(..., description="Abbreviation of the law")
    paragraph_nr: str = Field(..., description="Paragraph number")
    paragraph_text: str = Field(..., description="Text of the paragraph")
    absatz_nr: str = Field(..., description="Number of the section (Absatz)")
    satz_nr: str = Field(..., description="Sentence number within the section")
    markers: list[str] = Field(..., description="List of markers for subdivision of a sentence")
    satz_text: str = Field(..., description="Text of the sentence")


class LMJuristischerSatzWorkflowOutput(BaseModel):
    norm_typ_lvl_1: NormTyp
    norm_typ_lvl_2: SatzKategorie | None = None
    wenn_dann_satz: str | None = None
    tatbestandsmerkmale: list[str] | None = None
    atomare_tatbestandsmerkmale: list[AtomaresTBM] | None = None
    rechtsfolge: Rechtsfolge | None = None
    formel: str | None = None


class LMMateriellRechtlichWorkflowOutput(BaseModel):
    norm_typ_lvl_2: SatzKategorie = Field(..., description="Subcategory of the sentence (e.g., 'wenn-dann')")
    wenn_dann_satz: str | None = None
    tatbestandsmerkmale: list[str] | None = None
    atomare_tatbestandsmerkmale: list[AtomaresTBM] | None = None
    rechtsfolge: Rechtsfolge | None = None
    formel: str | None = None


class LMRfWorkflowInput(BaseModel):
    gesetz: str = Field(..., description="The law")
    paragraph_nr: str = Field(..., description="Paragraph number")
    absatz_nr: str = Field(..., description="Number of the section (Absatz)")
    satz_nr: str = Field(..., description="Sentence number within the section")
    rechtsfolge: str = Field(
        description="The legal consequence to be analyzed in the Lernmechanismus",
    )


class LMWennDannWorkflowOutput(BaseModel):
    wenn_dann_satz: str | None = None
    tatbestandsmerkmale: list[str] | None = None
    atomare_tatbestandsmerkmale: list[AtomaresTBM] | None = None
    rechtsfolge: Rechtsfolge | None = None
    formel: str | None = None


class LMHandlungsermaechtigungWorkflowInput(BaseModel):
    rechtsfolge: str = Field(..., description="The legal consequence to be analyzed in the Lernmechanismus")
