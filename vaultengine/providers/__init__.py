"""Provider registry. Importing this package registers the built-in backends."""

from __future__ import annotations

from .base import (Provider, ProviderError, available, get_provider,  # noqa: F401
                   parse_json_array, register)

# Import side effects register each provider under its name.
from . import null      # noqa: F401,E402  -> 'null'
from . import ollama    # noqa: F401,E402  -> 'ollama'
from . import openai_compat  # noqa: F401,E402  -> 'openai-compat'

__all__ = ["Provider", "ProviderError", "available", "get_provider",
           "parse_json_array", "register"]
