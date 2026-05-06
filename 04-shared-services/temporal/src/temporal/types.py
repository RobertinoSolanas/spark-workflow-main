"""Reusable Pydantic types for Temporal serialization."""

from __future__ import annotations

import base64
from typing import Annotated, Any

from pydantic import BeforeValidator, PlainSerializer


def _b64_decode(v: Any) -> bytes:
    if isinstance(v, str):
        return base64.b64decode(v)
    return v


Base64Bytes = Annotated[
    bytes,
    BeforeValidator(_b64_decode),
    PlainSerializer(lambda v: base64.b64encode(v).decode("ascii"), return_type=str),
]
"""bytes field that round-trips through JSON as base64.

Pydantic v2 tries to UTF-8 decode ``bytes`` for JSON serialization,
which fails on arbitrary binary data (e.g. PDFs).  Use this instead of
plain ``bytes`` on any Pydantic model that passes through Temporal.
"""
