# src/activities/enrichment_utils.py
"""
Shared utility functions for chunk enrichment activities.
"""

import re


def extract_table_text(html_content: str) -> str:
    """Extract readable text from HTML table by removing tags."""
    text = re.sub(r"<[^>]+>", " ", html_content)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 500:
        text = text[:500] + "..."
    return text
