"""ASGI entrypoint for `uvicorn src.api.main:app`."""

from src.api.app import create_app

app = create_app()
