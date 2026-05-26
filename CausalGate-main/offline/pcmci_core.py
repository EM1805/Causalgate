from __future__ import annotations

"""Offline full PCMCI entrypoint.

This module intentionally imports the real PCMCI Discovery engine directly.
There is no separate lazy/stub PCMCI path: CLI, tests, and package imports all
resolve to the same full engine implementation in ``pcmci_discovery_parts.engine``.
"""

from pcmci_discovery_parts.engine import ProposalEngine, build_argparser, cli, main
from pcmci_discovery_parts.config import ProposalConfig

__all__ = ["ProposalConfig", "ProposalEngine", "build_argparser", "main", "cli"]


if __name__ == "__main__":
    raise SystemExit(cli())
