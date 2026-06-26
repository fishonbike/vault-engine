"""vault-engine — identity de-identification for cloud LLM hand-off.

De-identify text before it goes to a cloud model, with a swappable local model
doing the detection and a reversible map kept on your machine.

    from vaultengine import deidentify, rehydrate, Config

    result = deidentify(open("notes.txt").read(), Config(policy="balanced"))
    send_to_cloud(result.text)          # tokens only — no real identities
    reply = get_cloud_reply()
    restored = rehydrate(reply, result.vault)   # real identities back, locally
"""

from __future__ import annotations

__version__ = "0.1.0"

from .config import Config                       # noqa: E402
from .mapping import Vault                        # noqa: E402
from .pipeline import Result, deidentify, rehydrate  # noqa: E402
from .providers import ProviderError, available, get_provider  # noqa: E402
from .spans import Span                           # noqa: E402

__all__ = [
    "__version__", "Config", "Vault", "Result", "Span",
    "deidentify", "rehydrate",
    "available", "get_provider", "ProviderError",
]
