# Prompt Injection Defense

A zero-dependency Python library providing centralized prompt injection defense utilities. Wraps system prompts with anti-injection preambles and sanitizes user inputs before they reach the LLM.

## Overview

The *Prompt Injection Defense* library provides:

- **System prompt wrapping**: Prepending and appending anti-injection preambles (DE/EN/VLM variants)
- **Input sanitization**: Stripping known prompt injection markers from arbitrary input dicts
- **Invisible character removal**: Detecting and removing steganographic Unicode payloads (categories Cf, Co, Cn)

## Installation

```bash
uv pip install prompt-injection
```

## Usage

### Wrapping System Prompts

```python
from prompt_injection.prompt_defense import wrap_system_prompt

# German preamble (default)
safe_prompt = wrap_system_prompt("Analysiere das Dokument.", lang="de")

# English preamble
safe_prompt = wrap_system_prompt("Analyze the document.", lang="en")

# VLM variant (for image-based inputs)
safe_prompt = wrap_system_prompt("Beschreibe das Bild.", lang="de", vlm=True)
```

### Sanitizing User Inputs

```python
from prompt_injection.prompt_defense import sanitize_external_data

clean = sanitize_external_data({"text": user_provided_text})
```

## Detected Injection Patterns

The sanitizer strips the following patterns from input text:

| Pattern                    | Target                                        |
| -------------------------- | --------------------------------------------- |
| `<\|word\|>`              | ChatML, Llama 3, Cohere special tokens        |
| `[INST]` / `[/INST]`      | Llama 2 instruction markers                   |
| `<<SYS>>` / `<</SYS>>`   | Llama 2 system tags                           |
| `<start_of_turn>` / `<end_of_turn>` | Gemini turn markers               |
| `### System:` / `### Assistant:` / … | Role-spoofing lines (case-insensitive) |
| Invisible Unicode          | Categories Cf (format), Co (private use), Cn (unassigned) |
