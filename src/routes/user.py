from flask import Blueprint, jsonify, request, session
from src.models.user import User, db

user_bp = Blueprint('user', __name__)

def require_api_login():
    if not session.get("admin_logged_in"):
        return jsonify({"success": False, "error": "Authentication required"}), 401
    return None

@user_bp.route('/users', methods=['GET'])
def get_users():
    auth = require_api_login()
    if auth:
        return auth
    users = User.query.all()
    return jsonify([user.to_dict() for user in users])

@user_bp.route('/users', methods=['POST'])
def create_user():
    auth = require_api_login()
    if auth:
        return auth
    data = request.json
    user = User(username=data['username'], email=data['email'])
    db.session.add(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201

@user_bp.route('/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    auth = require_api_login()
    if auth:
        return auth
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict())

@user_bp.route('/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    auth = require_api_login()
    if auth:
        return auth
    user = User.query.get_or_404(user_id)
    data = request.json
    user.username = data.get('username', user.username)
    user.email = data.get('email', user.email)
    db.session.commit()
    return jsonify(user.to_dict())

@user_bp.route('/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    auth = require_api_login()
    if auth:
        return auth
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return '', 204
