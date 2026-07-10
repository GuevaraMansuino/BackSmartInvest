"""
Archivo de compatibilidad para plataformas como Render que ejecutan por defecto 'gunicorn app:app'.
Reexporta la aplicación principal de FastAPI desde main.py.
"""
from main import app

__all__ = ["app"]
