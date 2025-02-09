## services/webinterface.py ##
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
import jwt
import os
from datetime import datetime, timedelta
import logging
from .switch_api import SwitchAPI
from .interfaces import SwitchMonitorInterface, HotspotServiceInterface
from .config import Config

logger = logging.getLogger(__name__)

class WebService:
    def __init__(self, switch_monitor: SwitchMonitorInterface, hotspot_service: HotspotServiceInterface):
        self.switch_monitor = switch_monitor
        self.hotspot_service = hotspot_service
        
        template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'web', 'templates'))
        static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'web', 'static'))
        
        self.app = Flask(__name__,
                        template_folder=template_dir,
                        static_folder=static_dir)
        
        self.config = Config()
        self.app.config['SECRET_KEY'] = self.config.get('jwt_secret', 'default_secret_key')
        
        self.setup_routes()

    def login_required(self, f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = session.get('token')
            if not token:
                return render_template('index.html', show_login=True)
            try:
                jwt.decode(token, self.app.config['SECRET_KEY'], algorithms=["HS256"])
            except:
                return render_template('index.html', show_login=True)
            return f(*args, **kwargs)
        return decorated

    def setup_routes(self):
        @self.app.route('/')
        @self.login_required
        def index():
            try:
                switch_api = SwitchAPI()
                
                # Port-VLAN Mapping vom Switch holen
                port_vlans = {}
                try:
                    port_info = switch_api.get_port_info()
                    for port in port_info:
                        port_id = port.get('portId')
                        if port_id and 1 <= port_id <= self.config.port_count:
                            port_vlans[port_id] = port.get('portVlanId', 1)
                except:
                    # Fallback wenn keine Daten vom Switch
                    port_vlans = {port: 1 for port in range(1, self.config.port_count + 1)}

                # VLAN-Farben und Namen aus der Konfiguration
                vlan_colors = {}
                vlan_names = {}
                
                for key, value in self.config._config.items():
                    if key.startswith('vlan') and '_color' in key:
                        try:
                            # Format: vlanX_NAME_color
                            parts = key.replace('vlan', '').split('_')
                            vlan_id = int(parts[0])
                            name = parts[1]
                            
                            # Parse RGB values
                            r, g, b = map(int, value.split(','))
                            vlan_colors[vlan_id] = f"rgb({r},{g},{b})"
                            vlan_names[vlan_id] = name
                        except (ValueError, IndexError):
                            continue

                return render_template('index.html', 
                                    show_login=False,
                                    port_vlans=port_vlans,
                                    vlan_colors=vlan_colors,
                                    vlan_names=vlan_names,
                                    script_running=True)
            except Exception as e:
                logger.error(f"Error rendering template: {e}")
                return str(e), 500

        @self.app.route('/api/status')
        @self.login_required
        def status():
            return jsonify({
                'hotspot_active': self.hotspot_service.is_active(),
                'switch_connected': self.switch_monitor.is_connected(),
                'uptime': self.switch_monitor.get_uptime()
            })

        @self.app.route('/login', methods=['POST'])
        def login():
            if request.is_json:
                # API Login
                data = request.get_json()
                username = data.get('username')
                password = data.get('password')
            else:
                # Form Login
                username = request.form.get('username')
                password = request.form.get('password')
            
            if username == self.config.username and password == self.config.password:
                token = jwt.encode({
                    'user': username,
                    'exp': datetime.utcnow() + timedelta(hours=8)
                }, self.app.config['SECRET_KEY'])
                session['token'] = token
                
                if request.is_json:
                    return jsonify({'status': 'success'})
                else:
                    return redirect(url_for('index'))
            
            return render_template('index.html', show_login=True, error="Invalid credentials")

        @self.app.route('/api/switch/port/<int:port_id>', methods=['POST'])
        @self.login_required
        def update_port(port_id):
            try:
                data = request.get_json()
                vlan_id = data.get('vlan')
                
                if not vlan_id:
                    return jsonify({'status': 'error', 'message': 'Missing VLAN ID'}), 400
                    
                switch_api = SwitchAPI()
                
                if switch_api.set_port_vlan(port_id, vlan_id):
                    return jsonify({'status': 'success'})
                return jsonify({'status': 'error', 'message': 'Failed to update port'}), 500
                    
            except Exception as e:
                logger.error(f"Error updating port: {e}")
                return jsonify({'status': 'error', 'message': str(e)}), 500

    def run(self, host='0.0.0.0', port=5000, debug=False):
        self.app.run(host=host, port=port, debug=debug)