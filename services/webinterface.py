## services/webinterface.py ##
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
import jwt
import os
from datetime import datetime, timedelta
import logging
import threading
from typing import Optional, Dict, Any
from .switch_api import SwitchAPI, SwitchAPIError
from .interfaces import SwitchMonitorInterface, HotspotServiceInterface
from .config import Config
from .utils import VLANColorManager

logger = logging.getLogger(__name__)

class WebService:
    """Web interface for switch management"""
    def __init__(self, switch_monitor: SwitchMonitorInterface, 
                 hotspot_service: HotspotServiceInterface):
        self.switch_monitor = switch_monitor
        self.hotspot_service = hotspot_service
        self.config = Config()
        self.app = self._create_app()
        self._api_cache_lock = threading.Lock()
        self._api_cache: Dict[str, Any] = {}
        self._cache_timeout = 5  # seconds

    def _create_app(self) -> Flask:
        """Create and configure Flask application"""
        template_dir = self._get_template_dir()
        static_dir = self._get_static_dir()

        app = Flask(__name__,
                   template_folder=template_dir,
                   static_folder=static_dir)

        app.config['SECRET_KEY'] = self.config.get('jwt_secret', 'default_secret_key')
        app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
        
        self._register_routes(app)
        return app

    def _get_template_dir(self) -> str:
        """Get template directory path"""
        return os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', 'web', 'templates'
        ))

    def _get_static_dir(self) -> str:
        """Get static files directory path"""
        return os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', 'web', 'static'
        ))

    def login_required(self, f):
        """Authentication decorator"""
        @wraps(f)
        def decorated(*args, **kwargs):
            token = session.get('token')
            if not token:
                return render_template('index.html', show_login=True)
            try:
                jwt.decode(token, self.app.config['SECRET_KEY'], 
                          algorithms=["HS256"])
            except jwt.InvalidTokenError:
                return render_template('index.html', show_login=True)
            return f(*args, **kwargs)
        return decorated

    def _register_routes(self, app: Flask):
        """Register application routes"""
        @app.route('/')
        @self.login_required
        def index():
            try:
                port_vlans = self._get_port_vlans()
                color_manager = VLANColorManager()
                vlan_colors, vlan_names = self._get_vlan_info()

                return render_template('index.html', 
                    show_login=False,
                    port_vlans=port_vlans,
                    vlan_colors=vlan_colors,
                    vlan_names=vlan_names,
                    script_running=True)
            except Exception as e:
                logger.error(f"Error rendering template: {e}")
                return str(e), 500

        @app.route('/api/status')
        @self.login_required
        def status():
            try:
                return jsonify({
                    'hotspot_active': self.hotspot_service.is_active(),
                    'switch_connected': self.switch_monitor.is_connected(),
                    'uptime': self.switch_monitor.get_uptime()
                })
            except Exception as e:
                logger.error(f"Error getting status: {e}")
                return jsonify({'error': str(e)}), 500

        @app.route('/login', methods=['POST'])
        def login():
            try:
                credentials = self._get_credentials()
                if not credentials:
                    return render_template('index.html', 
                        show_login=True, 
                        error="Invalid request format")

                if self._validate_credentials(*credentials):
                    token = self._generate_token(credentials[0])
                    session['token'] = token
                    
                    if request.is_json:
                        return jsonify({'status': 'success'})
                    return redirect(url_for('index'))

                return render_template('index.html', 
                    show_login=True, 
                    error="Invalid credentials")
            except Exception as e:
                logger.error(f"Login error: {e}")
                return render_template('index.html', 
                    show_login=True, 
                    error="System error")

        @app.route('/api/switch/port/<int:port_id>', methods=['POST'])
        @self.login_required
        def update_port(port_id):
            try:
                data = request.get_json()
                vlan_id = data.get('vlan')

                if not vlan_id:
                    return jsonify({
                        'status': 'error', 
                        'message': 'Missing VLAN ID'
                    }), 400

                switch_api = self._get_switch_api()
                if switch_api.set_port_vlan(port_id, vlan_id):
                    self._invalidate_cache()
                    return jsonify({'status': 'success'})
                
                return jsonify({
                    'status': 'error', 
                    'message': 'Failed to update port'
                }), 500

            except ValueError as e:
                logger.error(f"Invalid input: {e}")
                return jsonify({
                    'status': 'error', 
                    'message': str(e)
                }), 400
            except SwitchAPIError as e:
                logger.error(f"API error: {e}")
                return jsonify({
                    'status': 'error', 
                    'message': str(e)
                }), 503
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                return jsonify({
                    'status': 'error', 
                    'message': 'Internal server error'
                }), 500

    def _get_credentials(self) -> Optional[tuple]:
        """Extract credentials from request"""
        if request.is_json:
            data = request.get_json()
            return data.get('username'), data.get('password')
        return request.form.get('username'), request.form.get('password')

    def _validate_credentials(self, username: str, password: str) -> bool:
        """Validate user credentials"""
        return (username == self.config.username and 
                password == self.config.password)

    def _generate_token(self, username: str) -> str:
        """Generate JWT token"""
        return jwt.encode({
            'user': username,
            'exp': datetime.utcnow() + timedelta(hours=8)
        }, self.app.config['SECRET_KEY'])

    def _get_switch_api(self) -> SwitchAPI:
        """Get or create SwitchAPI instance"""
        switch_api = SwitchAPI()
        if not switch_api.login():
            raise SwitchAPIError("Failed to connect to switch")
        return switch_api

    def _get_port_vlans(self) -> Dict[int, int]:
        """Get port-VLAN mapping"""
        try:
            switch_api = self._get_switch_api()
            port_info = switch_api.get_port_info()
            port_vlans = {}
            
            for port in port_info:
                port_id = port.get('portId')
                if port_id and 1 <= port_id <= self.config.port_count:
                    port_vlans[port_id] = port.get('portVlanId', 1)
            
            return port_vlans
        except Exception as e:
            logger.error(f"Error getting port VLANs: {e}")
            return {port: 1 for port in range(1, self.config.port_count + 1)}

    def _get_vlan_info(self) -> tuple:
        """Get VLAN colors and names"""
        vlan_colors = {}
        vlan_names = {}

        for key, value in self.config._config.items():
            if key.startswith('vlan') and '_color' in key:
                try:
                    parts = key.replace('vlan', '').split('_')
                    vlan_id = int(parts[0])
                    name = parts[1]
                    
                    color_manager = VLANColorManager()
                    r, g, b = color_manager.get_vlan_color(vlan_id)
                    vlan_colors[vlan_id] = f"rgb({r},{g},{b})"
                    vlan_names[vlan_id] = name
                except (ValueError, IndexError) as e:
                    logger.error(f"Error parsing VLAN {key}: {e}")
                    continue

        return vlan_colors, vlan_names

    def _invalidate_cache(self):
        """Clear API response cache"""
        with self._api_cache_lock:
            self._api_cache.clear()

    def run(self, host: str = '0.0.0.0', port: int = 5000, 
            debug: bool = False):
        """Run web server"""
        self.app.run(host=host, port=port, debug=debug)