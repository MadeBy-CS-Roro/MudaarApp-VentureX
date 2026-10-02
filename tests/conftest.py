import os
# Existing tests call the API without a token as the demo persona.
os.environ.setdefault("MUDAR_ALLOW_ANON", "1")
