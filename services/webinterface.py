from flask import Flask, render_template, request, jsonify, session
from functools import wraps
import jwt
from datetime import datetime, timedelta
import logging
import subprocess
from ..src.main import SwitchMonitor
from hotspot import HotspotService
from .config import Config
from .switch_api import SwitchAPI

logger = logging.getLogger(__name__)

app = Flask(__name__)
config = Config()
app.config['SECRET_KEY'] = config.get('jwt_secret', 'default_secret_key')
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax'
)

def check_dependencies():
    try:
        subprocess.run(["nmcli", "--version"], check=True, capture_output=True)
        return True
    except ImportError:
        logger.error("Flask not installed. Please install with: pip install flask")
        return False
    except FileNotFoundError:
        logger.error("nmcli not found. Please install NetworkManager")
        return False

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = session.get('token')
        if not token:
            return render_template('index.html', show_login=True)
        try:
            jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
        except:
            return render_template('index.html', show_login=True)
        return f(*args, **kwargs)
    return decorated

@app.route('/')
@login_required

def status():
    return jsonify({
        'hotspot_active': HotspotService.is_active(),
        'switch_connected': SwitchMonitor.is_connected(),
        'uptime': SwitchMonitor.get_uptime
    })

def index():
    port_vlans = {i: 1 for i in range(1, config.port_count + 1)}
    vlan_colors = {
        int(k.replace('vlan', '').split('_')[0]): v 
        for k, v in config._config.items() 
        if k.startswith('vlan') and k.endswith('_color')
    }
    vlan_names = {
        int(k.replace('vlan', '').split('_')[0]): k.split('_')[1]
        for k, v in config._config.items()
        if k.startswith('vlan') and '_color' in k
    }
    
    return render_template('index.html', 
                         show_login=False,
                         port_vlans=port_vlans,
                         vlan_colors=vlan_colors,
                         vlan_names=vlan_names,
                         script_running=True)

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    
    if username == config.username and password == config.password:
        token = jwt.encode({
            'user': username,
            'exp': datetime.utcnow() + timedelta(hours=8)
        }, app.config['SECRET_KEY'])
        session['token'] = token
        return jsonify({'status': 'success'})
    
    return render_template('index.html', show_login=True, error="Invalid credentials")

@app.route('/api/switch/port/<int:port_id>', methods=['POST'])
@login_required
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

def run_webinterface(host='0.0.0.0', port=5000, debug=False):
    app.run(host=host, port=port, debug=debug)

class WebService:
    def __init__(self, switch_monitor: SwitchMonitor, hotspot_service: HotspotService):
        self.switch_monitor = switch_monitor
        self.hotspot_service = hotspot_service
        self.app = Flask(__name__)
        self.setup_routes()

    def setup_routes(self):
        @self.app.route('/api/status')
        @login_required
        def status():
            return jsonify({
                'hotspot_active': self.hotspot_service.is_active(),
                'switch_connected': self.switch_monitor.is_connected(),
                'uptime': self.switch_monitor.get_uptime()
            })

    def run(self, host='0.0.0.0', port=5000):
        self.app.run(host=host, port=port)

if __name__ == '__main__':
    run_webinterface()