## services/webinterface.py ##
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
import jwt
import os
import time
from datetime import datetime, timedelta
import logging
import threading
from typing import Optional, Dict, Any, Tuple
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
        self._api_cache: Dict[str, Dict] = {}
        self._api_cache_lock = threading.Lock()
        self._cache_timeout = 5  # seconds

    def _create_app(self) -> Flask:
        """Create and configure Flask application"""
        app = Flask(__name__,
                   template_folder=self._get_template_dir(),
                   static_folder=self._get_static_dir())
        
        app.config['SECRET_KEY'] = self.config.get('jwt_secret', 'default_secret_key')
        app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
        app.config['TEMPLATES_AUTO_RELOAD'] = True
        
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
                return redirect(url_for('login'))
            try:
                jwt.decode(token, self.app.config['SECRET_KEY'], algorithms=["HS256"])
                return f(*args, **kwargs)
            except jwt.InvalidTokenError:
                session.clear()
                return redirect(url_for('login'))
        return decorated

    def _register_routes(self, app: Flask) -> None:
        """Register all application routes"""
        
        @app.route('/')
        @self.login_required
        def index():
            try:
                port_vlans = self._get_port_vlans()
                vlan_colors, vlan_names = self._get_vlan_info()
                
                # Check switch connection
                switch_connected = False
                try:
                    api = self._get_switch_api()
                    switch_connected = True
                except:
                    pass

                return render_template('index.html',
                    show_login=False,
                    port_vlans=port_vlans,
                    vlan_colors=vlan_colors,
                    vlan_names=vlan_names,
                    script_running=switch_connected)
            except Exception as e:
                logger.error(f"Error rendering index: {e}")
                return render_template('error.html', error=str(e))

        @app.route('/login', methods=['GET', 'POST'])
        def login():
            if request.method == 'GET':
                if session.get('token'):
                    try:
                        jwt.decode(session['token'], self.app.config['SECRET_KEY'], algorithms=["HS256"])
                        return redirect(url_for('index'))
                    except jwt.InvalidTokenError:
                        session.clear()
                return render_template('index.html', show_login=True)
                
            username = request.form.get('username')
            password = request.form.get('password')
            
            if not username or not password:
                return render_template('index.html', 
                    show_login=True, 
                    error="Missing credentials")
                
            if self._validate_credentials(username, password):
                session.permanent = True
                token = self._generate_token(username)
                session['token'] = token
                response = redirect(url_for('index'))
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                return response
                
            return render_template('index.html', 
                show_login=True, 
                error="Invalid credentials")

        @app.route('/logout')
        def logout():
            session.clear()
            return redirect(url_for('login'))

        @app.route('/api/status')
        @self.login_required
        def status():
            try:
                # Einfache Verbindungsprüfung
                switch_connected = False
                try:
                    api = self._get_switch_api()
                    switch_connected = True
                except:
                    pass

                return jsonify({
                    'switch_connected': switch_connected,
                    'hotspot_active': self.hotspot_service.is_active(),
                    'uptime': time.time() - self.switch_monitor._start_time
                })
            except Exception as e:
                logger.error(f"Error getting status: {e}")
                return jsonify({'error': str(e)}), 500

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
                    
                if not 1 <= port_id <= self.config.port_count:
                    return jsonify({
                        'status': 'error',
                        'message': f'Invalid port ID: {port_id}'
                    }), 400
                    
                if not 1 <= vlan_id <= 4094:
                    return jsonify({
                        'status': 'error',
                        'message': f'Invalid VLAN ID: {vlan_id}'
                    }), 400

                switch_api = self._get_switch_api()
                if switch_api.set_port_vlan(port_id, vlan_id):
                    self._invalidate_cache()
                    return jsonify({'status': 'success'})
                    
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to update port'
                }), 500
                
            except SwitchAPIError as e:
                logger.error(f"Switch API error: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e)
                }), 503
            except Exception as e:
                logger.error(f"Unexpected error updating port: {e}")
                return jsonify({
                    'status': 'error',
                    'message': 'Internal server error'
                }), 500
            
        @app.route('/api/refresh', methods=['POST'])
        @self.login_required
        def refresh_data():
            try:
                self._invalidate_cache()
                port_vlans = self._get_port_vlans()
                vlan_colors, vlan_names = self._get_vlan_info()
                
                return jsonify({
                    'status': 'success',
                    'port_vlans': port_vlans,
                    'vlan_colors': vlan_colors,
                    'vlan_names': vlan_names
                })
            except Exception as e:
                logger.error(f"Error refreshing data: {e}")
                return jsonify({
                    'status': 'error',
                    'message': str(e)
                }), 500

    def _get_credentials(self) -> Tuple[Optional[str], Optional[str]]:
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
        """Get or create SwitchAPI instance with connection check"""
        switch_api = SwitchAPI()
        
        # Ensure we have a valid switch IP
        if not self.config.switch_ip:
            raise SwitchAPIError("No switch IP configured")
            
        # Set base URL before login
        switch_api.base_url = f"https://{self.config.switch_ip}{self.config.base_url_suffix}"
        
        if not switch_api.login():
            raise SwitchAPIError("Failed to connect to switch")
        return switch_api

    def _get_port_vlans(self) -> Dict[int, int]:
        """Get port-VLAN mapping with caching"""
        try:
            with self._api_cache_lock:
                cache_key = 'port_vlans'
                cached_data = self._api_cache.get(cache_key)
                if cached_data and (time.time() - cached_data['timestamp'] < self._cache_timeout):
                    return cached_data['data']

            switch_api = self._get_switch_api()
            port_info = switch_api.get_port_info()
            port_vlans = {}
            
            for port in port_info:
                port_id = port.get('portId')
                if port_id and 1 <= port_id <= self.config.port_count:
                    port_vlans[port_id] = port.get('portVlanId', 1)
            
            # Update cache
            with self._api_cache_lock:
                self._api_cache[cache_key] = {
                    'data': port_vlans,
                    'timestamp': time.time()
                }
            
            return port_vlans
        except Exception as e:
            logger.error(f"Error getting port VLANs: {e}")
            return {port: 1 for port in range(1, self.config.port_count + 1)}

    def _get_vlan_info(self) -> Tuple[Dict[int, str], Dict[int, str]]:
        """Get VLAN colors and names"""
        try:
            with self._api_cache_lock:
                cache_key = 'vlan_info'
                cached_data = self._api_cache.get(cache_key)
                if cached_data and (time.time() - cached_data['timestamp'] < self._cache_timeout):
                    return cached_data['data']

            vlan_colors = {}
            vlan_names = {}
            color_manager = VLANColorManager()

            # Get configured VLANs from config
            for key, value in self.config._config.items():
                if key.startswith('vlan') and '_color' in key:
                    try:
                        parts = key.replace('vlan', '').split('_')
                        vlan_id = int(parts[0])
                        name = parts[1]
                        
                        r, g, b = color_manager.get_vlan_color(vlan_id)
                        vlan_colors[vlan_id] = f"rgb({r},{g},{b})"
                        vlan_names[vlan_id] = name
                    except (ValueError, IndexError):
                        continue

            # Check switch for additional VLANs if scanning is enabled
            if self.config.scan_vlans:
                try:
                    switch_api = self._get_switch_api()
                    switch_vlans = switch_api.scan_vlans()
                    
                    for vlan_id, vlan_name in switch_vlans.items():
                        vlan_id = int(vlan_id)
                        if vlan_id not in vlan_colors:
                            r, g, b = color_manager.get_vlan_color(vlan_id)
                            vlan_colors[vlan_id] = f"rgb({r},{g},{b})"
                            vlan_names[vlan_id] = vlan_name
                except Exception as e:
                    logger.error(f"Error scanning switch VLANs: {e}")

            # Update cache
            with self._api_cache_lock:
                self._api_cache[cache_key] = {
                    'data': (vlan_colors, vlan_names),
                    'timestamp': time.time()
                }

            return vlan_colors, vlan_names
        except Exception as e:
            logger.error(f"Error getting VLAN info: {e}")
            return {}, {}

    def _invalidate_cache(self) -> None:
        """Clear API response cache"""
        with self._api_cache_lock:
            self._api_cache.clear()

    def run(self, host: str = '127.0.0.1', port: int = 5000, debug: bool = False) -> None:
        """Run the web interface"""
        try:
            logger.info(f"Starting web interface on {host}:{port}")
            logger.info(f"Template dir: {self._get_template_dir()}")
            logger.info(f"Static dir: {self._get_static_dir()}")
            
            self.app.run(
                host=host,
                port=port,
                debug=debug,
                use_reloader=False
            )
        except Exception as e:
            logger.error(f"Failed to start web interface: {e}")
            raise