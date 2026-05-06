#!/usr/bin/env python3
"""Entrypoint script for LiteLLM proxy"""

import os

if __name__ == "__main__":
    os.execvp(
        "litellm",
        [
            "litellm",
            "--config",
            "/app/config.yaml",
            "--port",
            "4000",
            "--host",
            "0.0.0.0",
        ],
    )
