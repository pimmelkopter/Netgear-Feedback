##services/wsgi.py##
from services.webinterface import WebService

def create_app():
    web_service = WebService()
    return web_service.app

app = create_app()