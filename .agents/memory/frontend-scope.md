---
name: Uploaded frontend scope
description: User's integration boundary for the uploaded Mawid app.
---

Backend changes are approved for the phone-app update. Port missing features from the uploaded backend without replacing current security, production checks, backup work, or wishlist fixes.

**Why:** The user explicitly replaced the previous frontend-only boundary in the phone-app update instructions.

**How to apply:** Merge features selectively rather than overwriting current backend files. Keep the demo provider data and safe-to-spend formula unchanged. All screens stay Arabic RTL and phone-width, including on desktop.