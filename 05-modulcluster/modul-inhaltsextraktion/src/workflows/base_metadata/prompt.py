# src/workflows/metadata_extraction/base/base_metadata_prompt.py
"""Prompts for the base metadata extraction workflow.

Note: All examples in this file use entirely fictional names, locations, and data.
They do not refer to any real infrastructure project, company, or municipality.
"""

GATHER_EVIDENCE_SYSTEM_PROMPT = """Based on the document text below, extract the following metadata. For each field, provide both the 'value' and the exact 'source' text snippet that justifies the value.

CRITICAL FORMAT RULES:
- Each field must have exactly TWO keys: "value" and "source"
- The "source" field must ALWAYS be a SINGLE STRING (never a list), containing the exact quote from the document
- For list-type fields (affected_municipalities, affected_federal_states), the "value" is a list of strings, but "source" remains ONE string
- If you cannot find a value, omit the entire field (do not include it with null value)

CORRECT FORMAT EXAMPLE:
{{
  "project_applicant": {{
    "value": "Nordwind Infrastruktur GmbH",
    "source": "Die Nordwind Infrastruktur GmbH als Vorhabenträger beantragt..."
  }},
  "affected_municipalities": {{
    "value": ["Lindenberg", "Weidenbach", "Hochfeld"],
    "source": "Die Strecke verläuft durch die Städte Lindenberg, Weidenbach und Hochfeld."
  }},
  "pipeline_length": {{
    "value": "45 km",
    "source": "Die geplante Leitung hat eine Gesamtlänge von 45 km."
  }}
}}

WRONG FORMAT (DO NOT USE):
{{
  "affected_municipalities": {{
    "value": [{{"value": "Lindenberg"}}, {{"value": "Weidenbach"}}],
    "source": ["Quote 1", "Quote 2"]
  }}
}}

Ensure your output is a clean JSON object without any markdown formatting. If a value is not found, omit the field entirely."""

GATHER_EVIDENCE_USER_TEMPLATE = """Here is the document text:
{external_data_tag_open}
{markdown_content}
{external_data_tag_close}
"""

CONSOLIDATE_EVIDENCE_SYSTEM_PROMPT = """You are a meticulous data analyst. Your task is to synthesize a list of metadata objects, extracted from different parts of a single document, into one definitive and accurate JSON object. Each object provides a 'value' and the 'source' text for that value.

Follow these field-specific instructions carefully:

1.  **`affected_municipalities` and `affected_federal_states` (List-based fields):**
    - First, collect all `value` arrays from all evidence objects into a single, flat list.
    - Remove any duplicate entries.
    - **Crucially, filter the final list to include only actual geographical locations (cities, municipalities, states).** For example, from a list like ["Gemeinde A", "Gemeinde B", "Industriegebiet Gemeinde C", "Abfallwirtschaftsbetrieb Gemeinde D"], the correct output is ["Gemeinde A", "Gemeinde B", "Gemeinde C", "Gemeinde D"].

2.  **`application_subject` (Detailed text field):**
    - Find all `source` texts for this field across all evidence objects.
    - Combine these texts into a single, comprehensive paragraph.
    - **Remove any markdown formatting or headers (e.g., '# 1.3 Antragsgegenstand') from the final text.** The goal is to have a clean, descriptive text block.
    - It should have details about the subject of the plannnig approval application, the object to be constructed and ancillary facilities.

3.  **All other single-value fields (e.g., `planning_company`, `project_applicant`):**
    - Examine all extracted `value` options and their corresponding `source` texts.
    - Choose the single value that is the most complete, specific, and official-sounding. For example, "Beispiel Planungs GmbH & Co. KG" is better than "Beispiel Planungs GmbH".
    - If you find conflicting but equally valid information, prioritize the value that appeared earliest in the document (i.e., from the first objects in the list).

Your final output must be a single, clean JSON object containing only the final, consolidated values."""

CONSOLIDATE_EVIDENCE_USER_TEMPLATE = """Here is the list of evidence objects:
{external_data_tag_open}
{evidence_list_json}
{external_data_tag_close}
"""
