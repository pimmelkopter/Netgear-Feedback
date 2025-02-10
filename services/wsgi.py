##services/wsgi.py##
import os
import logging
from typing import Optional
from flask import Flask
from services.webinterface import WebService
from services.switch_api import SwitchAPI
from src.main import SwitchMonitor
from services.hotspot import HotspotService
from services.config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AppFactory:
    """Factory for creating and configuring Flask application"""
    _instance: Optional[Flask] = None
    
    @classmethod
    def create_app(cls) -> Flask:
        """Create or return existing Flask application"""
        if cls._instance is None:
            try:
                # Initialize core services
                config = Config()
                switch_monitor = cls._init_switch_monitor()
                hotspot_service = cls._init_hotspot_service()
                
                # Create web service
                web_service = WebService(switch_monitor, hotspot_service)
                
                # Configure app
                cls._instance = web_service.app
                cls._configure_app(cls._instance, config)
                
                logger.info("Application initialized successfully")
                return cls._instance
                
            except Exception as e:
                logger.error(f"Failed to create application: {e}")
                raise
        
        return cls._instance
    
    @staticmethod
    def _init_switch_monitor() -> SwitchMonitor:
        """Initialize switch monitor service"""
        try:
            return SwitchMonitor()
        except Exception as e:
            logger.error(f"Failed to initialize switch monitor: {e}")
            raise
            
    @staticmethod
    def _init_hotspot_service() -> HotspotService:
        """Initialize hotspot service"""
        try:
            return HotspotService()
        except Exception as e:
            logger.error(f"Failed to initialize hotspot service: {e}")
            raise
            
    @staticmethod
    def _configure_app(app: Flask, config: Config):
        """Configure Flask application"""
        # Set environment-specific configurations
        app.config['ENV'] = os.getenv('FLASK_ENV', 'production')
        app.config['DEBUG'] = os.getenv('FLASK_DEBUG', '0') == '1'
        
        # Set session configuration
        app.config['SESSION_COOKIE_SECURE'] = True
        app.config['SESSION_COOKIE_HTTPONLY'] = True
        app.config['PERMANENT_SESSION_LIFETIME'] = 28800  # 8 hours
        
        # Set custom configuration from config service
        app.config['SECRET_KEY'] = config.get('jwt_secret', os.urandom(24))
        
        # Configure error handlers
        @app.errorhandler(404)
        def not_found_error(error):
            return "Page not found", 404
            
        @app.errorhandler(500)
        def internal_error(error):
            logger.error(f"Internal server error: {error}")
            return "Internal server error", 500

# Create application instance
app = AppFactory.create_app()

if __name__ == "__main__":
    # Run development server if executed directly
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)