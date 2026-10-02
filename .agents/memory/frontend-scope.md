---
name: Uploaded frontend scope
description: User's integration boundary for the uploaded Mawid app.
---

The user requested: “Add only the frontend to the current backend” and “link to backend.”

**Why:** The user chose frontend-only integration rather than importing the full uploaded app.

**How to apply:** Preserve the current backend and recent fixes when integrating the upload. Adapt the frontend to supported APIs; do not overwrite backend code with ZIP versions or add unsupported backend features as part of frontend integration.