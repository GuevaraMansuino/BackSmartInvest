import os

# Configuración automática de Gunicorn para ejecutar aplicaciones FastAPI (ASGI) con Uvicorn
worker_class = "uvicorn.workers.UvicornWorker"
workers = 1  # 1 worker óptimo para el nivel gratuito de Render
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
timeout = 120
