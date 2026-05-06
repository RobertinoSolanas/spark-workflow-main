# src/workflows/metadata_extraction/document/document_metadata_prompt.py
"""Prompt for the document-specific metadata extraction workflow.

Note: All examples in this file use entirely fictional names, locations, and data.
They do not refer to any real infrastructure project, company, or municipality.
"""

DOCUMENT_METADATA_SYSTEM_PROMPT = """Based on the text below, extract the following metadata:
- The main title of the document (combine main title and subtitle into a single string if both exist).
- The document type or category (e.g., "Antragsunterlage zum Planfeststellungsverfahren").

IMPORTANT: Each field must be a simple string value, NOT a nested object.

CORRECT FORMAT:
{{
  "title": "Neubau einer Erdkabeltrasse Nordhausen-Waldberg - Erläuterungsbericht (Unterlage 01.03)",
  "document_type": "Antragsunterlage zum Planfeststellungsverfahren"
}}

WRONG FORMAT (DO NOT USE):
{{
  "title": {{"main": "Neubau...", "sub": "Erläuterungsbericht"}},
  "document_type": "..."
}}

Ensure your output is a clean JSON object without any markdown formatting."""

DOCUMENT_METADATA_USER_TEMPLATE = """Here is the document text:
{external_data_tag_open}
{markdown_content}
{external_data_tag_close}
"""
