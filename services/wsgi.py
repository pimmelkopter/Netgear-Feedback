##services/wsgi.py##
from services.webinterface import WebService
from src.main import SwitchMonitor
from services.hotspot import HotspotService

def create_app():
    switch_monitor = SwitchMonitor()
    hotspot_service = HotspotService()
    web_service = WebService(switch_monitor, hotspot_service)
    return web_service.app

app = create_app()