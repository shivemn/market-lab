"""The web API: start a simulated day, read its events, and watch it play out over a WebSocket."""

from marketlab.api.app import create_app

__all__ = ["create_app"]
