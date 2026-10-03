---
name: Merge marker false positives
description: The merge completion check treats decorative equals-sign comments as unresolved conflict markers.
---

Avoid seven consecutive equals signs in decorative comments.

**Why:** The merge completion check rejects these even inside normal JavaScript comments, rather than matching only standalone Git conflict separator lines.

**How to apply:** If merge completion reports remaining markers but a line-anchored search finds none, search for marker substrings anywhere and replace decorative separators with hyphens.