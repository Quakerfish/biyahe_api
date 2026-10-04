# Vercel's Python runtime looks for a FastAPI instance named `app` at a
# recognized entrypoint (app.py/index.py/main.py/etc. at the project root,
# or under src/, app/, or api/). This file just re-exports the real app so
# Vercel finds it here, while the actual app still lives in app/main.py
# (handy for running locally too: `uvicorn app.main:app --reload`).
from app.main import app  # noqa: F401
