---
name: Python merge environment
description: Python package installation behaves differently in merge hooks than in the interactive workspace.
---

Post-merge hooks do not inherit the interactive workspace's pip target configuration.

**Why:** A plain pip install in the hook attempted to modify immutable Nix system Python and failed with an externally-managed-environment error, despite normal dependency installation working in the workspace.

**How to apply:** Keep hook installations explicitly targeted to the project's Python package directory and include it in the hook's Python import path. Do not override system-package protections or create a virtual environment.