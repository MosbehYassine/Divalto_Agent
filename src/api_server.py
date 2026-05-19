"""Compatibility entrypoint for uvicorn api_server:app."""
from app.server import app

__all__ = ["app"]
