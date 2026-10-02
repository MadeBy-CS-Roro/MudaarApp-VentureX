---
name: Archive replacement integrity
description: Handling incomplete archives when replacing the full application.
---

A full-app replacement does not authorize silently combining recovered archive files with existing app files. If an archive is incomplete, leave the app unchanged and offer a newly exported complete archive or explicitly approved partial recovery.

**Why:** Repeated uploads of the same truncated archive can contain valid frontend and backend files while omitting unknown later changes. Passing tests on a recovered mix would not prove that it matches the requested full app.

**How to apply:** Validate archive completeness before overwriting application files. If the user approves partial recovery, only recover complete, checksum-verified entries; preserve saved data and disclose that missing files remain from the existing app.