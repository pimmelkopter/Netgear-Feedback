from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_wtf.csrf import CSRFProtect, generate_csrf
from functools import wraps
import jwt
import os
from datetime import datetime, timedelta
import logging
import subprocess
from .switch_api import SwitchAPI
from .interfaces import SwitchMonitorInterface, HotspotServiceInterface
from .config import Config

logger = logging.getLogger(__name__)

class WebService:
    def __init__(self, switch_monitor: SwitchMonitorInterface, hotspot_service: HotspotServiceInterface):
        self.switch_monitor = switch_monitor
        self.hotspot_service = hotspot_service
        
        # Template und Static Pfade
        template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'web', 'templates'))
        static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'web', 'static'))
        
        self.app = Flask(__name__,
                        template_folder=template_dir,
                        static_folder=static_dir)
        
        self.config = Config()
        self.app.config['SECRET_KEY'] = self.config.get('jwt_secret', 'default_secret_key')
        self.app.config['WTF_CSRF_SECRET_KEY'] = self.config.get('jwt_secret', 'default_secret_key')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.app.config.update(
            SESSION_COOKIE_SECURE=True,
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE='Lax',
            WTF_CSRF_CHECK_DEFAULT=False  # Nur für ausgewählte Routes aktivieren
        )
        
        # CSRF Protection initialisieren
        self.csrf = CSRFProtect(self.app)
        
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
        
        csrf = CSRFProtect()
        csrf.init_app(self.app)
        
        @self.app.context_processor
        def utility_processor():
            def get_csrf_token():
                return generate_csrf()
            return dict(csrf_token=get_csrf_token)
        
        @self.app.route('/')
        @self.login_required
        def index():
            try:
                port_vlans = {i: 1 for i in range(1, self.config.port_count + 1)}
                vlan_colors = {
                    int(k.replace('vlan', '').split('_')[0]): v 
                    for k, v in self.config._config.items() 
                    if k.startswith('vlan') and k.endswith('_color')
                }
                vlan_names = {
                    int(k.replace('vlan', '').split('_')[0]): k.split('_')[1]
                    for k, v in self.config._config.items()
                    if k.startswith('vlan') and '_color' in k
                }
                
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

        @self.app.context_processor
        def inject_csrf_token():
            return dict(csrf_token=generate_csrf())

        @self.app.after_request
        def add_csrf_cookie(response):
            if 'csrf_token' not in session:
                session['csrf_token'] = generate_csrf()
            return response

    def run(self, host='0.0.0.0', port=5000, debug=False):
        self.app.run(host=host, port=port, debug=debug)