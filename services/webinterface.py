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
                # Default VLAN für alle Ports ist 1
                port_vlans = {i: 1 for i in range(1, self.config.port_count + 1)}
                
                # VLAN Farben und Namen aus der Konfiguration extrahieren
                vlan_colors = {}
                vlan_names = {}
                
                for key, value in self.config._config.items():
                    if key.startswith('vlan') and key.endswith('_color'):
                        try:
                            # Extrahiere VLAN ID und ignoriere leere oder ungültige Werte
                            vlan_id_str = key.replace('vlan', '').split('_')[0]
                            if vlan_id_str and vlan_id_str.isdigit():
                                vlan_id = int(vlan_id_str)
                                vlan_colors[vlan_id] = value
                                
                                # Finde den zugehörigen Namen
                                name_key = f"vlan{vlan_id}_name"
                                vlan_names[vlan_id] = self.config.get(name_key, f"VLAN {vlan_id}")
                        except (ValueError, IndexError) as e:
                            logger.warning(f"Skipping invalid VLAN config entry: {key} - {e}")
                            continue
                
                # Stelle sicher, dass mindestens VLAN 1 existiert
                if not vlan_colors:
                    vlan_colors[1] = "#808080"  # Standard-Grau
                    vlan_names[1] = "Default VLAN"
                
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