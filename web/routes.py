from flask import Blueprint, request, jsonify, current_app
from functools import wraps
import jwt
import logging
from ..services.config import Config
from ..services.switch_api import SwitchAPI

logger = logging.getLogger(__name__)
api_bp = Blueprint('api', __name__)
config = Config()

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing'}), 401
        try:
            jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=["HS256"])
        except:
            return jsonify({'message': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated

@api_bp.route('/api/switch/port/<int:port_id>', methods=['POST'])
@token_required
def update_port(port_id):
    data = request.get_json()
    
    if not data or 'vlan' not in data:
        return jsonify({'error': 'Missing VLAN data'}), 400
        
    try:
        switch_api = SwitchAPI()
        if switch_api.set_port_vlan(port_id, data['vlan']):
            return jsonify({'status': 'success'})
        return jsonify({'status': 'error'}), 500
    except Exception as e:
        logger.error(f"Error updating port: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/api/switch/config', methods=['POST'])
@token_required
def save_config():
    try:
        switch_api = SwitchAPI()
        if switch_api.save_config():
            return jsonify({'status': 'success'})
        return jsonify({'status': 'error'}), 500
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/api/switch/port/<int:port_id>', methods=['GET'])
@token_required
def get_port_info(port_id):
    try:
        switch_api = SwitchAPI()
        info = switch_api.get_port_info(port_id)
        if info:
            return jsonify(info)
        return jsonify({'error': 'Failed to get port info'}), 500
    except Exception as e:
        logger.error(f"Error getting port info: {e}")
        return jsonify({'error': str(e)}), 500