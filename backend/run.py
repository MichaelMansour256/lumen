"""Start the API server:  python run.py"""
import uvicorn

from app.config import load_settings
from app.main import create_app

if __name__ == "__main__":
    settings = load_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="info")
