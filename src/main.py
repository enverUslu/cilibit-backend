import os
import sys
import json
import uuid
import threading
import time
import base64
import secrets
import urllib.error
import urllib.parse
import urllib.request
import hashlib
from datetime import datetime, timedelta
from werkzeug.exceptions import NotFound
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for
from flask_cors import CORS

# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))
SECRET_KEY = os.getenv('SECRET_KEY', '').strip()
if not SECRET_KEY and os.getenv('FLASK_ENV') == 'production':
    raise RuntimeError('SECRET_KEY must be set in production')
app.config['SECRET_KEY'] = SECRET_KEY or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)
# Allow up to 100MB uploads for large GIF files
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB

# Enable CORS for all routes
cors_origins = os.getenv('CORS_ORIGINS', '*').split(',') if os.getenv('CORS_ORIGINS') else ['*']
CORS(app, 
     origins=cors_origins,
     methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
     allow_headers=['Content-Type', 'Authorization', 'Cache-Control'],
     max_age=600,
     supports_credentials=True)

ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', '').strip()
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', '')


def is_logged_in():
    return session.get("admin_logged_in") is True


def require_login():
    if not is_logged_in():
        return redirect(url_for("login"))
    return None


def require_api_login():
    if not is_logged_in():
        return jsonify({"success": False, "error": "Authentication required"}), 401
    return None


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("serve", path=""))
        return send_from_directory(app.static_folder, 'login.html')
    return send_from_directory(app.static_folder, 'login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for("login"))

# Data directory
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

# Upload directories
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
PROFILE_UPLOAD_DIR = os.path.join(UPLOAD_DIR, 'profiles')
CILIBIT_UPLOAD_DIR = os.path.join(UPLOAD_DIR, 'cilibits')
TICKET_UPLOAD_DIR = os.path.join(UPLOAD_DIR, 'tickets')
os.makedirs(PROFILE_UPLOAD_DIR, exist_ok=True)
os.makedirs(CILIBIT_UPLOAD_DIR, exist_ok=True)
os.makedirs(TICKET_UPLOAD_DIR, exist_ok=True)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB

# Data file paths
CILIBITS_FILE = os.path.join(DATA_DIR, 'cilibits.json')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
SETTINGS_FILE = os.path.join(DATA_DIR, 'settings.json')
CHATS_FILE = os.path.join(DATA_DIR, 'chats.json')
MESSAGES_FILE = os.path.join(DATA_DIR, 'messages.json')
CAMPFIRE_STATE_FILE = os.path.join(DATA_DIR, 'campfire_state.json')
CAMPFIRE_ASSETS_FILE = os.path.join(DATA_DIR, 'campfire_assets.json')
CAMPFIRE_READ_SESSIONS_FILE = os.path.join(DATA_DIR, 'campfire_read_sessions.json')
CAMPFIRE_SHARED_FILE = os.path.join(DATA_DIR, 'campfire_shared.json')
AKADEMIK_PROGRESS_FILE = os.path.join(DATA_DIR, 'akademik_progress.json')
SPOTIFY_TOKENS_FILE = os.path.join(DATA_DIR, 'spotify_tokens.json')
TICKETS_FILE = os.path.join(DATA_DIR, 'tickets.json')
TV_CATALOG_FILE = os.path.join(DATA_DIR, 'tv_catalog.json')
NOTES_FILE = os.path.join(DATA_DIR, 'notes.json')

CILIBIT_USERS = {
    username: password
    for username, password in {
        'enver': os.getenv('CILIBIT_ENVER_PASSWORD', ''),
        'irem': os.getenv('CILIBIT_IREM_PASSWORD', ''),
    }.items()
    if password
}
CAMPFIRE_EVENT_TYPES = {
    'join', 'state', 'chat', 'emote', 'leave', 'typing',
    'who?', 'wall', 'room', 'wall?', 'room?', 'move', 'shared', 'dm', 'activity'
}
CAMPFIRE_STATE_MAX_BYTES = 20 * 1024 * 1024
CAMPFIRE_ASSET_MAX_BYTES = 3 * 1024 * 1024
CAMPFIRE_EVENTS = []
CAMPFIRE_EVENT_SEQUENCE = 0
CAMPFIRE_EVENT_LOCK = threading.Lock()
CAMPFIRE_EVENT_CONDITION = threading.Condition(CAMPFIRE_EVENT_LOCK)
CAMPFIRE_FILE_LOCK = threading.RLock()

def load_json_file(filepath, default_data):
    """Load JSON data from file, create with default if doesn't exist"""
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            save_json_file(filepath, default_data)
            return default_data
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return default_data

def save_json_file(filepath, data):
    """Save data to JSON file"""
    try:
        with CAMPFIRE_FILE_LOCK:
            temp_path = f"{filepath}.tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, filepath)
        return True
    except Exception as e:
        print(f"Error saving {filepath}: {e}")
        return False

def load_cilibits():
    """Load cilibits from JSON file"""
    return load_json_file(CILIBITS_FILE, [])

def save_cilibits(cilibits):
    """Save cilibits to JSON file"""
    return save_json_file(CILIBITS_FILE, cilibits)

def load_users():
    """Load users from JSON file"""
    return load_json_file(USERS_FILE, {})

def save_users(users):
    """Save users to JSON file"""
    return save_json_file(USERS_FILE, users)

def load_settings():
    """Load settings from JSON file"""
    return load_json_file(SETTINGS_FILE, {})

def save_settings(settings):
    """Save settings to JSON file"""
    return save_json_file(SETTINGS_FILE, settings)

def load_chats():
    """Load chats from JSON file"""
    return load_json_file(CHATS_FILE, [])

def save_chats(chats):
    """Save chats to JSON file"""
    return save_json_file(CHATS_FILE, chats)

def load_messages():
    """Load messages from JSON file"""
    return load_json_file(MESSAGES_FILE, [])

def save_messages(messages):
    """Save messages to JSON file"""
    return save_json_file(MESSAGES_FILE, messages)

def current_cilibit_user():
    username = session.get('cilibit_user')
    return username if username in CILIBIT_USERS else None

def require_cilibit_user():
    username = current_cilibit_user()
    if not username:
        return None, (jsonify({'success': False, 'error': 'Cilibit login required'}), 401)
    return username, None

def _spotify_config():
    return {
        'client_id': os.getenv('SPOTIFY_CLIENT_ID', '').strip(),
        'client_secret': os.getenv('SPOTIFY_CLIENT_SECRET', '').strip(),
        'redirect_uri': os.getenv(
            'SPOTIFY_REDIRECT_URI',
            'https://api.enverelectronics.com/api/spotify/callback',
        ).strip(),
        'frontend_url': os.getenv(
            'CILIBIT_FRONTEND_URL',
            'https://enverelectronics.com/cilibit/',
        ).strip(),
    }

def _spotify_return_url(candidate):
    configured = _spotify_config()['frontend_url']
    if not candidate:
        return configured
    try:
        target = urllib.parse.urlparse(candidate)
        allowed = urllib.parse.urlparse(configured)
        if target.scheme in ('http', 'https') and target.netloc == allowed.netloc:
            return candidate
        if target.hostname in ('localhost', '127.0.0.1'):
            return candidate
    except ValueError:
        pass
    return configured

def _spotify_token_request(payload, use_pkce=False):
    config = _spotify_config()
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    if use_pkce:
        payload = dict(payload, client_id=config['client_id'])
    else:
        credentials = base64.b64encode(
            f"{config['client_id']}:{config['client_secret']}".encode('utf-8')
        ).decode('ascii')
        headers['Authorization'] = f'Basic {credentials}'
    token_request = urllib.request.Request(
        'https://accounts.spotify.com/api/token',
        data=urllib.parse.urlencode(payload).encode('utf-8'),
        headers=headers,
        method='POST',
    )
    try:
        with urllib.request.urlopen(token_request, timeout=12) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode('utf-8')).get('error_description')
        except Exception:
            detail = None
        raise RuntimeError(detail or f'Spotify token request failed ({exc.code})') from exc

def _save_spotify_token(username, token, previous=None):
    tokens = load_json_file(SPOTIFY_TOKENS_FILE, {})
    saved = dict(previous or tokens.get(username, {}))
    saved.update(token)
    saved['expires_at'] = int(time.time() * 1000) + int(token.get('expires_in', 3600)) * 1000
    tokens[username] = saved
    if not save_json_file(SPOTIFY_TOKENS_FILE, tokens):
        raise RuntimeError('Failed to save Spotify token')
    return saved

def json_size(data):
    return len(json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))

def load_campfire_states():
    return load_json_file(CAMPFIRE_STATE_FILE, {})

def load_campfire_assets():
    return load_json_file(CAMPFIRE_ASSETS_FILE, {})

def load_campfire_read_sessions():
    return load_json_file(CAMPFIRE_READ_SESSIONS_FILE, {})

def load_tickets():
    tickets = load_json_file(TICKETS_FILE, [])
    return tickets if isinstance(tickets, list) else []

def save_tickets(tickets):
    return save_json_file(TICKETS_FILE, tickets)

def load_tv_catalog():
    catalog = load_json_file(TV_CATALOG_FILE, [])
    return catalog if isinstance(catalog, list) else []

def save_tv_catalog(catalog):
    return save_json_file(TV_CATALOG_FILE, catalog)

def load_notes():
    notes = load_json_file(NOTES_FILE, [])
    return notes if isinstance(notes, list) else []

def save_notes(notes):
    return save_json_file(NOTES_FILE, notes)

SHARED_SCENE_KEYS = {
    'campfire.props.v2', 'campfire.props.custom.v1',
    'campfire.bg.v1', 'campfire.mode.v1',
}
SHARED_THEME_KEYS = {
}

def _shared_defaults():
    states = load_campfire_states()
    enver_storage = states.get('enver', {}).get('storage', {})
    now = int(time.time() * 1000)
    return {
        'revision': 1,
        'updatedAt': now,
        'updatedBy': 'enver',
        'scopes': {
            'scene': {
                'revision': 1,
                'storage': {key: enver_storage[key] for key in SHARED_SCENE_KEYS if key in enver_storage},
            },
            'theme': {
                'revision': 1,
                'storage': {key: enver_storage[key] for key in SHARED_THEME_KEYS if key in enver_storage},
            },
        },
    }

def load_campfire_shared():
    if not os.path.exists(CAMPFIRE_SHARED_FILE):
        shared = _shared_defaults()
        save_json_file(CAMPFIRE_SHARED_FILE, shared)
        return shared
    shared = load_json_file(CAMPFIRE_SHARED_FILE, _shared_defaults())
    scopes = shared.setdefault('scopes', {})
    scopes.setdefault('scene', {'revision': 1, 'storage': {}})
    scopes.setdefault('theme', {'revision': 1, 'storage': {}})
    scopes['theme']['storage'] = {}
    return shared

def publish_campfire_event(actor, event_type, payload):
    global CAMPFIRE_EVENT_SEQUENCE
    with CAMPFIRE_EVENT_CONDITION:
        CAMPFIRE_EVENT_SEQUENCE += 1
        event = {
            'seq': CAMPFIRE_EVENT_SEQUENCE,
            'type': event_type,
            'from': actor,
            'ts': int(time.time() * 1000),
            'data': payload,
        }
        CAMPFIRE_EVENTS.append(event)
        del CAMPFIRE_EVENTS[:-500]
        CAMPFIRE_EVENT_CONDITION.notify_all()
    return event

def migrate_cilibits_add_likes():
    """Add likes and dislikes fields to existing cilibits if they don't exist"""
    cilibits = load_cilibits()
    updated = False
    
    for cilibit in cilibits:
        if 'likes' not in cilibit:
            cilibit['likes'] = []
            updated = True
        if 'dislikes' not in cilibit:
            cilibit['dislikes'] = []
            updated = True
    
    if updated:
        save_cilibits(cilibits)
        print("Migrated cilibits to include likes/dislikes")

# API Routes

@app.route('/api/test', methods=['GET'])
def test():
    """Health check endpoint"""
    return jsonify({
        'success': True,
        'message': 'Cilibit API is running',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/session', methods=['GET', 'POST', 'DELETE'])
def cilibit_session():
    """Create and inspect the private enver/irem app session."""
    if request.method == 'GET':
        username = current_cilibit_user()
        return jsonify({'success': True, 'authenticated': bool(username), 'username': username})

    if request.method == 'DELETE':
        session.pop('cilibit_user', None)
        return jsonify({'success': True})

    data = request.get_json(silent=True) or {}
    username = str(data.get('username', '')).strip().lower()
    password = str(data.get('password', ''))
    if username not in CILIBIT_USERS or password != CILIBIT_USERS[username]:
        return jsonify({'success': False, 'error': 'Invalid username or password'}), 401

    session['cilibit_user'] = username
    session.permanent = True
    return jsonify({'success': True, 'authenticated': True, 'username': username})

@app.route('/api/spotify/connect', methods=['GET'])
def spotify_connect():
    """Begin Spotify OAuth for the current private Cilibit user."""
    actor, error = require_cilibit_user()
    if error:
        return error
    config = _spotify_config()
    if not config['client_id']:
        return jsonify({'success': False, 'error': 'Spotify is not configured'}), 503

    state = secrets.token_urlsafe(24)
    session['spotify_oauth_state'] = state
    session['spotify_return_url'] = _spotify_return_url(request.args.get('return_to'))
    params = {
        'client_id': config['client_id'],
        'response_type': 'code',
        'redirect_uri': config['redirect_uri'],
        'state': state,
        'scope': 'user-read-currently-playing user-read-playback-state user-modify-playback-state',
        'show_dialog': 'true',
    }
    if not config['client_secret']:
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode('ascii')).digest()
        ).rstrip(b'=').decode('ascii')
        session['spotify_code_verifier'] = verifier
        params.update({'code_challenge_method': 'S256', 'code_challenge': challenge})
    else:
        session.pop('spotify_code_verifier', None)
    return redirect(f"https://accounts.spotify.com/authorize?{urllib.parse.urlencode(params)}")

@app.route('/api/spotify/callback', methods=['GET'])
def spotify_callback():
    """Exchange Spotify's authorization code and return to Cilibit."""
    actor, error = require_cilibit_user()
    if error:
        return error
    state = request.args.get('state', '')
    expected_state = session.pop('spotify_oauth_state', '')
    return_url = _spotify_return_url(session.pop('spotify_return_url', None))
    if not state or not secrets.compare_digest(state, expected_state):
        return jsonify({'success': False, 'error': 'Invalid Spotify authorization state'}), 400
    if request.args.get('error'):
        return redirect(return_url)

    code = request.args.get('code', '')
    if not code:
        return jsonify({'success': False, 'error': 'Spotify authorization code is missing'}), 400
    config = _spotify_config()
    verifier = session.pop('spotify_code_verifier', '')
    token_payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': config['redirect_uri'],
    }
    if verifier:
        token_payload['code_verifier'] = verifier
    try:
        token = _spotify_token_request(token_payload, use_pkce=bool(verifier))
        token['auth_mode'] = 'pkce' if verifier else 'secret'
        _save_spotify_token(actor, token)
    except RuntimeError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 502
    return redirect(return_url)

@app.route('/api/spotify/token', methods=['GET'])
def spotify_token():
    """Return a current short-lived Spotify access token to the player."""
    actor, error = require_cilibit_user()
    if error:
        return error
    tokens = load_json_file(SPOTIFY_TOKENS_FILE, {})
    saved = tokens.get(actor)
    if not saved or not saved.get('access_token'):
        return jsonify({'success': False, 'error': 'Spotify is not connected'}), 404

    if int(saved.get('expires_at', 0)) <= int(time.time() * 1000) + 60000:
        refresh_token = saved.get('refresh_token')
        config = _spotify_config()
        use_pkce = saved.get('auth_mode') == 'pkce'
        if not refresh_token or not config['client_id'] or (not use_pkce and not config['client_secret']):
            return jsonify({'success': False, 'error': 'Spotify authorization expired'}), 401
        try:
            refreshed = _spotify_token_request({
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
            }, use_pkce=use_pkce)
            saved = _save_spotify_token(actor, refreshed, saved)
        except RuntimeError as exc:
            return jsonify({'success': False, 'error': str(exc)}), 502

    return jsonify({
        'success': True,
        'accessToken': saved['access_token'],
        'expiresAt': saved['expires_at'],
    })

@app.route('/api/campfire/state/<username>', methods=['GET', 'PUT'])
def campfire_state(username):
    """Persist the standalone frontend's existing per-user state shapes."""
    actor, error = require_cilibit_user()
    if error:
        return error
    if username not in CILIBIT_USERS:
        return jsonify({'success': False, 'error': 'Unknown user'}), 404

    states = load_campfire_states()
    if request.method == 'GET':
        return jsonify({
            'success': True,
            'username': username,
            'state': states.get(username, {}),
        })

    if actor != username:
        return jsonify({'success': False, 'error': 'You can only update your own state'}), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'error': 'State must be an object'}), 400
    state = data.get('state', data)
    if not isinstance(state, dict):
        return jsonify({'success': False, 'error': 'State must be an object'}), 400
    if json_size(state) > CAMPFIRE_STATE_MAX_BYTES:
        return jsonify({'success': False, 'error': 'State is too large'}), 413

    states[username] = state
    if not save_json_file(CAMPFIRE_STATE_FILE, states):
        return jsonify({'success': False, 'error': 'Failed to save state'}), 500
    return jsonify({'success': True, 'username': username, 'state': state})

@app.route('/api/campfire/assets', methods=['GET', 'PUT'])
def campfire_assets():
    """Persist pixel-studio assets separately from smaller UI state."""
    actor, error = require_cilibit_user()
    if error:
        return error
    username = request.args.get('username', actor)
    if username not in CILIBIT_USERS:
        return jsonify({'success': False, 'error': 'Unknown user'}), 404

    all_assets = load_campfire_assets()
    if request.method == 'GET':
        return jsonify({'success': True, 'username': username, 'assets': all_assets.get(username, [])})

    if username != actor:
        return jsonify({'success': False, 'error': 'You can only update your own assets'}), 403
    data = request.get_json(silent=True) or {}
    assets = data.get('assets')
    if not isinstance(assets, list):
        return jsonify({'success': False, 'error': 'Assets must be an array'}), 400
    if len(assets) > 60:
        return jsonify({'success': False, 'error': 'At most 60 assets are allowed'}), 400
    if any(not isinstance(asset, dict) or json_size(asset) > CAMPFIRE_ASSET_MAX_BYTES for asset in assets):
        return jsonify({'success': False, 'error': 'An asset is invalid or too large'}), 413

    previous_assets = all_assets.get(username, [])
    all_assets[username] = assets
    if not save_json_file(CAMPFIRE_ASSETS_FILE, all_assets):
        return jsonify({'success': False, 'error': 'Failed to save assets'}), 500
    if len(assets) > len(previous_assets):
        newest = assets[-1] if assets else {}
        publish_campfire_event(actor, 'activity', {
            'action': 'studio_asset',
            'kind': newest.get('kind', 'decoration'),
            'name': newest.get('name', ''),
        })
    return jsonify({'success': True, 'username': username, 'assets': assets})

@app.route('/api/campfire/read-sessions', methods=['GET', 'PUT'])
def campfire_read_sessions():
    actor, error = require_cilibit_user()
    if error:
        return error
    username = request.args.get('username', actor)
    if username not in CILIBIT_USERS:
        return jsonify({'success': False, 'error': 'Unknown user'}), 404

    all_sessions = load_campfire_read_sessions()
    if request.method == 'GET':
        return jsonify({'success': True, 'username': username, 'sessions': all_sessions.get(username, [])})

    if username != actor:
        return jsonify({'success': False, 'error': 'You can only update your own sessions'}), 403
    data = request.get_json(silent=True) or {}
    sessions = data.get('sessions')
    if not isinstance(sessions, list):
        return jsonify({'success': False, 'error': 'Sessions must be an array'}), 400
    sessions = sessions[-500:]
    if json_size(sessions) > 1024 * 1024:
        return jsonify({'success': False, 'error': 'Reading history is too large'}), 413

    all_sessions[username] = sessions
    if not save_json_file(CAMPFIRE_READ_SESSIONS_FILE, all_sessions):
        return jsonify({'success': False, 'error': 'Failed to save reading history'}), 500
    return jsonify({'success': True, 'username': username, 'sessions': sessions})

@app.route('/api/campfire/bootstrap', methods=['GET'])
def campfire_bootstrap():
    actor, error = require_cilibit_user()
    if error:
        return error
    states = load_campfire_states()
    users = load_users()
    return jsonify({
        'success': True,
        'username': actor,
        'state': states.get(actor, {}),
        'shared': load_campfire_shared(),
        'profiles': {
            username: {
                'nickname': profile.get('nickname', username),
                'bio': profile.get('bio', ''),
                'profilePicture': profile.get('profilePicture', ''),
                'banner': profile.get('banner', ''),
                'hasSoundEffect': bool(profile.get('soundEffect', '')),
            }
            for username, profile in users.items() if username in CILIBIT_USERS
        },
    })

@app.route('/api/campfire/shared', methods=['GET', 'PATCH'])
def campfire_shared():
    actor, error = require_cilibit_user()
    if error:
        return error
    shared = load_campfire_shared()
    if request.method == 'GET':
        return jsonify({'success': True, 'shared': shared})

    data = request.get_json(silent=True) or {}
    scope_name = data.get('scope')
    storage = data.get('storage')
    if scope_name != 'scene' or not isinstance(storage, dict):
        return jsonify({'success': False, 'error': 'A valid scope and storage object are required'}), 400
    allowed = SHARED_SCENE_KEYS
    cleaned = {key: value for key, value in storage.items() if key in allowed and isinstance(value, str)}
    if not cleaned or json_size(cleaned) > CAMPFIRE_STATE_MAX_BYTES:
        return jsonify({'success': False, 'error': 'Shared update is empty or too large'}), 400

    with CAMPFIRE_FILE_LOCK:
        shared = load_campfire_shared()
        scope = shared.setdefault('scopes', {}).setdefault(scope_name, {'revision': 0, 'storage': {}})
        scope.setdefault('storage', {}).update(cleaned)
        scope['revision'] = int(scope.get('revision', 0)) + 1
        shared['revision'] = int(shared.get('revision', 0)) + 1
        shared['updatedAt'] = int(time.time() * 1000)
        shared['updatedBy'] = actor
        if not save_json_file(CAMPFIRE_SHARED_FILE, shared):
            return jsonify({'success': False, 'error': 'Failed to save shared state'}), 500

    payload = {'scope': scope_name, 'storage': cleaned, 'revision': scope['revision']}
    publish_campfire_event(actor, 'shared', payload)
    return jsonify({'success': True, 'shared': shared, 'update': payload})

@app.route('/api/campfire/events', methods=['GET', 'POST'])
def campfire_events():
    """Small polling event stream for the two-person live campfire."""
    actor, error = require_cilibit_user()
    if error:
        return error

    if request.method == 'GET':
        try:
            after = max(0, int(request.args.get('after', 0)))
        except ValueError:
            after = 0
        with CAMPFIRE_EVENT_CONDITION:
            if CAMPFIRE_EVENT_SEQUENCE <= after:
                CAMPFIRE_EVENT_CONDITION.wait(timeout=15)
            events = [
                event for event in CAMPFIRE_EVENTS
                if event['seq'] > after and (event['from'] != actor or event['type'] == 'activity')
            ]
            latest = CAMPFIRE_EVENT_SEQUENCE
        return jsonify({'success': True, 'events': events, 'latest': latest})

    data = request.get_json(silent=True) or {}
    event_type = data.get('type')
    payload = data.get('data', {})
    if event_type not in CAMPFIRE_EVENT_TYPES:
        return jsonify({'success': False, 'error': 'Unsupported event type'}), 400
    if not isinstance(payload, dict) or json_size(payload) > 512 * 1024:
        return jsonify({'success': False, 'error': 'Event payload is invalid or too large'}), 413

    event = publish_campfire_event(actor, event_type, payload)
    return jsonify({'success': True, 'event': event})

@app.route('/api/chat-test', methods=['GET'])
def chat_test():
    """Test chat functionality"""
    try:
        actor, error = require_cilibit_user()
        if error:
            return error
        chats = load_chats()
        messages = load_messages()
        return jsonify({
            'success': True,
            'chats_count': len(chats),
            'messages_count': len(messages),
            'message': 'Chat system test successful'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Chat system test failed'
        }), 500

@app.route('/api/frontend-test', methods=['GET'])
def frontend_test():
    """Simple test for frontend connectivity"""
    return jsonify({
        'success': True,
        'message': 'Frontend can reach backend!',
        'server_port': os.getenv('PORT', 'unknown'),
        'cors_origins': os.getenv('CORS_ORIGINS', 'not set')
    })

@app.route('/api/users', methods=['GET'])
@app.route('/users', methods=['GET'])  # Add both routes for compatibility
def get_users():
    """Get all users"""
    auth = require_api_login()
    if auth:
        return auth
    try:
        users = load_users()
        
        # Convert users dict to list format for API response
        users_list = []
        for username, user_data in users.items():
            users_list.append({
                'username': username,
                'nickname': user_data.get('nickname', username),
                'bio': user_data.get('bio', ''),
                'profilePicture': user_data.get('profilePicture', ''),
                'darkMode': user_data.get('darkMode', False),
                'soundEffect': user_data.get('soundEffect', ''),
                'banner': user_data.get('banner', ''),
                'hasSoundEffect': bool(user_data.get('soundEffect', ''))
            })
        
        return jsonify({
            'success': True,
            'users': users_list,
            'count': len(users_list)
        })
    except Exception as e:
        print(f"Error getting users: {e}")
        return jsonify({'success': False, 'error': 'Failed to fetch users'}), 500

# Chat API Routes
@app.route('/api/chats', methods=['GET'])
def get_user_chats():
    """Get all chats for a user"""
    try:
        username, error = require_cilibit_user()
        if error:
            return error
        
        chats = load_chats()
        messages = load_messages()
        users = load_users()
        
        # Build detailed chat list with last messages and unread counts
        user_chats = []
        for chat in chats:
            if username in chat['participants']:
                # Find other participant
                other_participant = 'test'
                for p in chat['participants']:
                    if p != username:
                        other_participant = p
                        break
                
                # Get chat messages to find last message and unread count
                chat_messages = [m for m in messages if m['chatId'] == chat['id']]
                chat_messages.sort(key=lambda x: x.get('timestamp', 0))
                
                # Find last message
                last_message = None
                if chat_messages:
                    last_msg = chat_messages[-1]
                    last_message = {
                        'content': last_msg['content'],
                        'timestamp': last_msg['timestamp'],
                        'sender': last_msg['sender']
                    }
                
                # Count unread messages
                unread_count = 0
                for msg in chat_messages:
                    if msg['sender'] != username and not msg.get('isRead', False):
                        unread_count += 1
                
                # Get user profile info for other participant
                other_user_profile = {
                    'username': other_participant,
                    'nickname': other_participant,
                    'profilePicture': ''
                }
                
                # Find user details
                if other_participant in users:
                    user_data = users[other_participant]
                    other_user_profile = {
                        'username': other_participant,
                        'nickname': user_data.get('nickname', other_participant),
                        'profilePicture': user_data.get('profilePicture', '')
                    }
                
                simple_chat = {
                    'id': chat['id'],
                    'participants': chat['participants'],
                    'lastMessage': last_message,
                    'unreadCount': unread_count,
                    'otherParticipant': other_user_profile
                }
                user_chats.append(simple_chat)
        
        # Sort chats by last message timestamp (newest first)
        user_chats.sort(key=lambda x: x['lastMessage']['timestamp'] if x['lastMessage'] else 0, reverse=True)
        
        return jsonify({
            'success': True,
            'chats': user_chats
        })
        
    except Exception as e:
        print(f"Error getting chats: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Failed to fetch chats: {str(e)}'}), 500

@app.route('/api/chats', methods=['POST'])
def create_or_get_chat():
    """Create a new chat or get existing chat between users"""
    try:
        actor, error = require_cilibit_user()
        if error:
            return error
        data = request.get_json()
        if not data or not data.get('participants') or len(data['participants']) < 2:
            return jsonify({'success': False, 'error': 'At least 2 participants are required'}), 400
        
        participants = sorted(data['participants'])  # Sort for consistent ordering
        if actor not in participants or any(participant not in CILIBIT_USERS for participant in participants):
            return jsonify({'success': False, 'error': 'Invalid chat participants'}), 403
        chats = load_chats()
        
        # Check if chat already exists between these participants
        existing_chat = None
        for chat in chats:
            if sorted(chat['participants']) == participants:
                existing_chat = chat
                break
        
        if existing_chat:
            return jsonify({'success': True, 'chat': existing_chat, 'isNew': False})
        
        # Create new chat
        new_chat = {
            'id': str(int(datetime.now().timestamp() * 1000)),
            'participants': participants,
            'createdAt': int(datetime.now().timestamp() * 1000),
            'lastActivity': int(datetime.now().timestamp() * 1000)
        }
        
        chats.append(new_chat)
        
        if save_chats(chats):
            publish_campfire_event(actor, 'dm', {'action': 'chat', 'chat': new_chat})
            return jsonify({'success': True, 'chat': new_chat, 'isNew': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to create chat'}), 500
            
    except Exception as e:
        print(f"Error creating chat: {e}")
        return jsonify({'success': False, 'error': 'Failed to create chat'}), 500

@app.route('/api/chats/<chat_id>/messages', methods=['GET'])
def get_chat_messages(chat_id):
    """Get messages for a specific chat"""
    try:
        username, error = require_cilibit_user()
        if error:
            return error
        
        chats = load_chats()
        messages = load_messages()
        
        # Verify user is participant in this chat
        chat = None
        for c in chats:
            if c['id'] == chat_id:
                if username in c['participants']:
                    chat = c
                    break
                else:
                    return jsonify({'success': False, 'error': 'Not authorized to view this chat'}), 403
        
        if not chat:
            return jsonify({'success': False, 'error': 'Chat not found'}), 404
        
        # Get messages for this chat
        chat_messages = [m for m in messages if m['chatId'] == chat_id]
        chat_messages.sort(key=lambda x: x.get('timestamp', 0))
        
        # Mark messages as read for this user
        updated = False
        for message in chat_messages:
            if message['sender'] != username:
                if not message.get('isRead', False):
                    message['isRead'] = True
                    updated = True
        if updated:
            save_messages(messages)
            publish_campfire_event(username, 'dm', {'action': 'read', 'chatId': chat_id})
        
        return jsonify({
            'success': True,
            'messages': chat_messages,
            'chat': chat
        })
        
    except Exception as e:
        print(f"Error getting messages: {e}")
        return jsonify({'success': False, 'error': 'Failed to fetch messages'}), 500

@app.route('/api/chats/<chat_id>/messages', methods=['POST'])
def send_message(chat_id):
    """Send a message to a chat"""
    try:
        actor, error = require_cilibit_user()
        if error:
            return error
        data = request.get_json()
        if not data or not data.get('content'):
            return jsonify({'success': False, 'error': 'Content is required'}), 400
        
        chats = load_chats()
        messages = load_messages()
        
        # Verify chat exists and user is participant
        chat = None
        for c in chats:
            if c['id'] == chat_id:
                if actor in c['participants']:
                    chat = c
                    break
                else:
                    return jsonify({'success': False, 'error': 'Not authorized to send to this chat'}), 403
        
        if not chat:
            return jsonify({'success': False, 'error': 'Chat not found'}), 404
        
        # Create new message
        new_message = {
            'id': str(int(datetime.now().timestamp() * 1000)),
            'chatId': chat_id,
            'sender': actor,
            'content': data['content'],
            'timestamp': int(datetime.now().timestamp() * 1000),
            'isRead': False,
            'type': data.get('type', 'text'),  # text, image
            'image': data.get('image', '')
        }
        
        messages.append(new_message)
        
        # Update chat last activity
        chat['lastActivity'] = new_message['timestamp']
        
        if save_messages(messages) and save_chats(chats):
            publish_campfire_event(actor, 'dm', {'action': 'message', 'chatId': chat_id, 'message': new_message})
            return jsonify({'success': True, 'message': new_message})
        else:
            return jsonify({'success': False, 'error': 'Failed to send message'}), 500
            
    except Exception as e:
        print(f"Error sending message: {e}")
        return jsonify({'success': False, 'error': 'Failed to send message'}), 500

@app.route('/api/chats/<chat_id>/mark-read', methods=['POST'])
def mark_messages_read(chat_id):
    """Mark all messages in a chat as read for a user"""
    try:
        username, error = require_cilibit_user()
        if error:
            return error
        
        chats = load_chats()
        if not any(chat['id'] == chat_id and username in chat.get('participants', []) for chat in chats):
            return jsonify({'success': False, 'error': 'Chat not found'}), 404
        messages = load_messages()
        
        # Mark messages as read
        updated = False
        for message in messages:
            if message['chatId'] == chat_id and message['sender'] != username:
                if not message.get('isRead', False):
                    message['isRead'] = True
                    updated = True
        
        if updated and save_messages(messages):
            publish_campfire_event(username, 'dm', {'action': 'read', 'chatId': chat_id})
            return jsonify({'success': True})
        else:
            return jsonify({'success': True})  # No updates needed
            
    except Exception as e:
        print(f"Error marking messages as read: {e}")
        return jsonify({'success': False, 'error': 'Failed to mark messages as read'}), 500

@app.route('/api/chats/<chat_id>/messages/<message_id>', methods=['DELETE'])
def delete_message(chat_id, message_id):
    """Delete a message from a chat"""
    try:
        username, error = require_cilibit_user()
        if error:
            return error
        
        messages = load_messages()
        chats = load_chats()
        
        # Verify chat exists and user is participant
        chat = None
        for c in chats:
            if c['id'] == chat_id:
                if username in c['participants']:
                    chat = c
                    break
                else:
                    return jsonify({'success': False, 'error': 'Not authorized to delete from this chat'}), 403
        
        if not chat:
            return jsonify({'success': False, 'error': 'Chat not found'}), 404
        
        # Find and delete the message (only if sender owns it)
        message_found = False
        for i, message in enumerate(messages):
            if message['id'] == message_id and message['chatId'] == chat_id:
                if message['sender'] == username:
                    messages.pop(i)
                    message_found = True
                    break
                else:
                    return jsonify({'success': False, 'error': 'You can only delete your own messages'}), 403
        
        if not message_found:
            return jsonify({'success': False, 'error': 'Message not found'}), 404
        
        if save_messages(messages):
            publish_campfire_event(username, 'dm', {'action': 'delete', 'chatId': chat_id, 'messageId': message_id})
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to save changes'}), 500
            
    except Exception as e:
        print(f"Error deleting message: {e}")
        return jsonify({'success': False, 'error': 'Failed to delete message'}), 500

@app.route('/api/cilibits', methods=['GET'])
def get_cilibits():
    """Get paginated cilibits"""
    try:
        actor, error = require_cilibit_user()
        if error:
            return error
        # Ensure migration on first load
        migrate_cilibits_add_likes()
        
        # Get pagination parameters
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 5))  # Default 5 per page
        
        cilibits = load_cilibits()
        
        # Filter out replies (only show top-level cilibits in main feed)
        top_level_cilibits = [c for c in cilibits if not c.get('parentId')]
        
        # Sort by timestamp (newest first)
        top_level_cilibits.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        
        # Calculate pagination
        total_items = len(top_level_cilibits)
        total_pages = max(1, (total_items + limit - 1) // limit)  # Ceiling division
        
        # Ensure page is within bounds
        page = max(1, min(page, total_pages))
        
        # Calculate slice indices
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        
        # Get paginated results
        paginated_cilibits = top_level_cilibits[start_idx:end_idx]
        
        return jsonify({
            'success': True,
            'topLevelCilibits': paginated_cilibits,
            'cilibits': cilibits,  # Still return all cilibits for replies
            'pagination': {
                'currentPage': page,
                'totalPages': total_pages,
                'totalItems': total_items,
                'itemsPerPage': limit,
                'hasNext': page < total_pages,
                'hasPrev': page > 1
            }
        })
    except Exception as e:
        print(f"Error getting cilibits: {e}")
        return jsonify({'success': False, 'error': 'Failed to fetch cilibits'}), 500

@app.route('/api/cilibits', methods=['POST'])
def create_cilibit():
    """Create a new cilibit"""
    try:
        actor, error = require_cilibit_user()
        if error:
            return error
        data = request.get_json()
        if not data or not data.get('content'):
            return jsonify({'success': False, 'error': 'Content is required'}), 400
        
        cilibits = load_cilibits()
        
        # Create new cilibit
        new_cilibit = {
            'id': str(int(datetime.now().timestamp() * 1000)),
            'content': data['content'],
            'timestamp': int(datetime.now().timestamp() * 1000),
            'author': actor,
            'parentId': data.get('parentId'),
            'image': data.get('image'),
            'isGif': data.get('isGif', False),
            'isCulubut': data.get('isCulubut', False),
            'type': data.get('type'),
            'likes': [],
            'dislikes': []
        }
        
        cilibits.append(new_cilibit)
        
        if save_cilibits(cilibits):
            action = 'culubut' if new_cilibit['isCulubut'] else ('cilibit_image' if new_cilibit['image'] else 'cilibit')
            publish_campfire_event(actor, 'activity', {
                'action': action,
                'cilibitId': new_cilibit['id'],
                'parentId': new_cilibit['parentId'],
            })
            return jsonify({'success': True, 'cilibit': new_cilibit})
        else:
            return jsonify({'success': False, 'error': 'Failed to save cilibit'}), 500
            
    except Exception as e:
        print(f"Error creating cilibit: {e}")
        return jsonify({'success': False, 'error': 'Failed to create cilibit'}), 500

@app.route('/api/cilibits/like', methods=['POST'])
def like_cilibit():
    """Like a cilibit"""
    try:
        username, error = require_cilibit_user()
        if error:
            return error
        data = request.get_json()
        if not data or not data.get('id'):
            return jsonify({'success': False, 'error': 'Cilibit ID is required'}), 400
        
        cilibits = load_cilibits()
        cilibit_id = data['id']
        
        # Find the cilibit
        cilibit = None
        for c in cilibits:
            if c['id'] == cilibit_id:
                cilibit = c
                break
        
        if not cilibit:
            return jsonify({'success': False, 'error': 'Cilibit not found'}), 404
        
        # Toggle like
        if username in cilibit['likes']:
            cilibit['likes'].remove(username)
            liked = False
        else:
            cilibit['likes'].append(username)
            # Remove from dislikes if present
            if username in cilibit['dislikes']:
                cilibit['dislikes'].remove(username)
            liked = True
        
        if save_cilibits(cilibits):
            return jsonify({
                'success': True,
                'liked': liked,
                'likesCount': len(cilibit['likes']),
                'dislikesCount': len(cilibit['dislikes'])
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to save like'}), 500
            
    except Exception as e:
        print(f"Error liking cilibit: {e}")
        return jsonify({'success': False, 'error': 'Failed to like cilibit'}), 500

@app.route('/api/cilibits/dislike', methods=['POST'])
def dislike_cilibit():
    """Dislike a cilibit"""
    try:
        username, error = require_cilibit_user()
        if error:
            return error
        data = request.get_json()
        if not data or not data.get('id'):
            return jsonify({'success': False, 'error': 'Cilibit ID is required'}), 400
        
        cilibits = load_cilibits()
        cilibit_id = data['id']
        
        # Find the cilibit
        cilibit = None
        for c in cilibits:
            if c['id'] == cilibit_id:
                cilibit = c
                break
        
        if not cilibit:
            return jsonify({'success': False, 'error': 'Cilibit not found'}), 404
        
        # Toggle dislike
        if username in cilibit['dislikes']:
            cilibit['dislikes'].remove(username)
            disliked = False
        else:
            cilibit['dislikes'].append(username)
            # Remove from likes if present
            if username in cilibit['likes']:
                cilibit['likes'].remove(username)
            disliked = True
        
        if save_cilibits(cilibits):
            return jsonify({
                'success': True,
                'disliked': disliked,
                'likesCount': len(cilibit['likes']),
                'dislikesCount': len(cilibit['dislikes'])
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to save dislike'}), 500
            
    except Exception as e:
        print(f"Error disliking cilibit: {e}")
        return jsonify({'success': False, 'error': 'Failed to dislike cilibit'}), 500

@app.route('/api/cilibits/delete', methods=['POST'])
def delete_cilibit():
    """Delete a cilibit"""
    try:
        username, error = require_cilibit_user()
        if error:
            return error
        data = request.get_json()
        if not data or not data.get('id'):
            return jsonify({'success': False, 'error': 'Cilibit ID is required'}), 400
        
        cilibits = load_cilibits()
        cilibit_id = data['id']
        
        # Find and verify ownership
        cilibit_index = None
        for i, c in enumerate(cilibits):
            if c['id'] == cilibit_id:
                if c['author'] == username:
                    cilibit_index = i
                    break
                else:
                    return jsonify({'success': False, 'error': 'Not authorized to delete this cilibit'}), 403
        
        if cilibit_index is None:
            return jsonify({'success': False, 'error': 'Cilibit not found'}), 404
        
        # Delete the cilibit
        cilibits.pop(cilibit_index)
        
        if save_cilibits(cilibits):
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to delete cilibit'}), 500
            
    except Exception as e:
        print(f"Error deleting cilibit: {e}")
        return jsonify({'success': False, 'error': 'Failed to delete cilibit'}), 500

@app.route('/api/profile/<username>', methods=['GET'])
def get_profile(username):
    """Get user profile with cilibits"""
    try:
        actor, error = require_cilibit_user()
        if error:
            return error
        if username not in CILIBIT_USERS:
            return jsonify({'error': 'Profile not found'}), 404
        users = load_users()
        cilibits = load_cilibits()
        
        # Get user profile or create default
        user_profile = users.get(username, {
            'nickname': username,
            'bio': '',
            'profilePicture': '',
            'darkMode': False,
            'soundEffect': '',
            'banner': ''
        })
        
        # Get user's cilibits
        user_cilibits = [c for c in cilibits if c.get('author') == username]
        user_cilibits.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        
        # Return profile with cilibits and sound effect status
        profile_with_cilibits = {
            **user_profile,
            'cilibits': user_cilibits,
            'hasSoundEffect': bool(user_profile.get('soundEffect', ''))
        }
        
        return jsonify(profile_with_cilibits)
        
    except Exception as e:
        print(f"Error getting profile for {username}: {e}")
        return jsonify({'error': 'Failed to fetch profile'}), 500

@app.route('/api/profile/<username>', methods=['POST'])
def update_profile(username):
    """Update user profile"""
    try:
        actor, error = require_cilibit_user()
        if error:
            return error
        if actor != username:
            return jsonify({'success': False, 'error': 'You can only update your own profile'}), 403
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        users = load_users()
        
        # Get existing profile or create new
        user_profile = users.get(username, {
            'nickname': username,
            'bio': '',
            'profilePicture': '',
            'darkMode': False,
            'soundEffect': '',
            'banner': ''
        })
        
        # Update fields
        if 'nickname' in data:
            user_profile['nickname'] = data['nickname']
        if 'bio' in data:
            user_profile['bio'] = data['bio']
        if 'profilePicture' in data:
            user_profile['profilePicture'] = data['profilePicture']
        if 'darkMode' in data:
            user_profile['darkMode'] = data['darkMode']
        if 'soundEffect' in data:
            user_profile['soundEffect'] = data['soundEffect']
        if 'banner' in data:
            user_profile['banner'] = data['banner']
        
        # Save updated profile
        users[username] = user_profile
        
        if save_users(users):
            return jsonify({
                'success': True, 
                'profile': {
                    **user_profile,
                    'hasSoundEffect': bool(user_profile.get('soundEffect', ''))
                }
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to save profile'}), 500
            
    except Exception as e:
        print(f"Error updating profile for {username}: {e}")
        return jsonify({'success': False, 'error': 'Failed to update profile'}), 500

@app.route('/api/profile/<username>/sound', methods=['GET'])
def get_user_sound_effect(username):
    """Get user's sound effect"""
    try:
        actor, error = require_cilibit_user()
        if error:
            return error
        if username not in CILIBIT_USERS:
            return jsonify({'success': False, 'error': 'Profile not found'}), 404
        users = load_users()
        user_profile = users.get(username, {})
        sound_effect = user_profile.get('soundEffect', '')
        
        if sound_effect:
            return jsonify({
                'success': True,
                'soundEffect': sound_effect,
                'hasSoundEffect': True
            })
        else:
            return jsonify({
                'success': True,
                'soundEffect': '',
                'hasSoundEffect': False
            })
            
    except Exception as e:
        print(f"Error getting sound effect for {username}: {e}")
        return jsonify({'success': False, 'error': 'Failed to fetch sound effect'}), 500

@app.route('/api/debug', methods=['GET'])
def debug():
    """Debug endpoint to show current data"""
    try:
        auth = require_api_login()
        if auth:
            return auth
        cilibits = load_cilibits()
        users = load_users()
        settings = load_settings()
        
        return jsonify({
            'success': True,
            'data': {
                'cilibits_count': len(cilibits),
                'users_count': len(users),
                'settings': settings,
                'recent_cilibits': cilibits[:5] if cilibits else [],
                'user_list': list(users.keys())
            }
        })
    except Exception as e:
        print(f"Error in debug: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/reset-kv', methods=['POST'])
def reset_data():
    """Reset all data (development only)"""
    try:
        if os.getenv('ALLOW_RESET_KV') != '1':
            return jsonify({'success': False, 'error': 'Not found'}), 404
        auth = require_api_login()
        if auth:
            return auth
        # Clear all data files
        save_cilibits([])
        save_users({})
        save_settings({})
        
        return jsonify({
            'success': True,
            'message': 'All data has been reset'
        })
    except Exception as e:
        print(f"Error resetting data: {e}")
        return jsonify({'success': False, 'error': 'Failed to reset data'}), 500


# Add these routes to your main.py file (after existing routes)

# Colobot data file path
COLOBOTS_FILE = os.path.join(DATA_DIR, 'colobots.json')

def load_colobots():
    """Load colobots from JSON file"""
    return load_json_file(COLOBOTS_FILE, [])

def save_colobots(colobots):
    """Save colobots to JSON file"""
    return save_json_file(COLOBOTS_FILE, colobots)

@app.route('/api/colobots', methods=['GET'])
def get_colobots():
    """Get all colobots or colobots for a specific date"""
    try:
        actor, error = require_cilibit_user()
        if error:
            return error
        date_filter = request.args.get('date')  # Format: YYYY-MM-DD
        colobots = load_colobots()
        
        if date_filter:
            # Filter colobots by date
            filtered_colobots = [c for c in colobots if c.get('date') == date_filter]
            return jsonify({
                'success': True,
                'colobots': filtered_colobots,
                'count': len(filtered_colobots)
            })
        else:
            # Return all colobots, sorted by date (newest first)
            colobots.sort(key=lambda x: x.get('date', ''), reverse=True)
            return jsonify({
                'success': True,
                'colobots': colobots,
                'count': len(colobots)
            })
            
    except Exception as e:
        print(f"Error getting colobots: {e}")
        return jsonify({'success': False, 'error': 'Failed to fetch colobots'}), 500

@app.route('/api/colobots', methods=['POST'])
def create_colobot():
    """Create a new colobot"""
    try:
        actor, error = require_cilibit_user()
        if error:
            return error
        data = request.get_json()
        if not data or not data.get('title') or not data.get('content'):
            return jsonify({'success': False, 'error': 'Title and content are required'}), 400
        
        colobots = load_colobots()
        
        # Get today's date
        today = datetime.now().strftime('%Y-%m-%d')
        
        colobot_date = data.get('date', today)
        try:
            datetime.strptime(colobot_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({'success': False, 'error': 'Date must use YYYY-MM-DD'}), 400
        
        # Create new colobot
        new_colobot = {
            'id': str(int(datetime.now().timestamp() * 1000)),
            'title': data['title'],
            'content': data['content'],
            'birdImage': data.get('birdImage', ''),
            'author': actor,
            'date': colobot_date,
            'timestamp': int(datetime.now().timestamp() * 1000),
            'tags': data.get('tags', [])
        }
        
        colobots.append(new_colobot)
        
        if save_colobots(colobots):
            publish_campfire_event(actor, 'activity', {
                'action': 'colobot',
                'colobotId': new_colobot['id'],
            })
            return jsonify({'success': True, 'colobot': new_colobot})
        else:
            return jsonify({'success': False, 'error': 'Failed to save colobot'}), 500
            
    except Exception as e:
        print(f"Error creating colobot: {e}")
        return jsonify({'success': False, 'error': 'Failed to create colobot'}), 500

@app.route('/api/colobots/<colobot_id>', methods=['GET'])
def get_colobot(colobot_id):
    """Get a specific colobot by ID"""
    try:
        actor, error = require_cilibit_user()
        if error:
            return error
        colobots = load_colobots()
        
        colobot = None
        for c in colobots:
            if c['id'] == colobot_id:
                colobot = c
                break
        
        if not colobot:
            return jsonify({'success': False, 'error': 'Colobot not found'}), 404
        
        return jsonify({'success': True, 'colobot': colobot})
        
    except Exception as e:
        print(f"Error getting colobot: {e}")
        return jsonify({'success': False, 'error': 'Failed to fetch colobot'}), 500

@app.route('/api/colobots/<colobot_id>', methods=['PUT'])
def update_colobot(colobot_id):
    """Update a colobot"""
    try:
        actor, error = require_cilibit_user()
        if error:
            return error
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        colobots = load_colobots()
        
        # Find the colobot
        colobot_index = None
        for i, c in enumerate(colobots):
            if c['id'] == colobot_id:
                # Check if user is author
                if c['author'] != actor:
                    return jsonify({'success': False, 'error': 'Not authorized to edit this colobot'}), 403
                colobot_index = i
                break
        
        if colobot_index is None:
            return jsonify({'success': False, 'error': 'Colobot not found'}), 404
        
        # Update colobot fields
        colobot = colobots[colobot_index]
        if 'title' in data:
            colobot['title'] = data['title']
        if 'content' in data:
            colobot['content'] = data['content']
        if 'birdImage' in data:
            colobot['birdImage'] = data['birdImage']
        if 'tags' in data:
            colobot['tags'] = data['tags']
        if 'date' in data:
            try:
                datetime.strptime(data['date'], '%Y-%m-%d')
            except ValueError:
                return jsonify({'success': False, 'error': 'Date must use YYYY-MM-DD'}), 400
            colobot['date'] = data['date']
        
        # Update timestamp
        colobot['lastModified'] = int(datetime.now().timestamp() * 1000)
        
        if save_colobots(colobots):
            return jsonify({'success': True, 'colobot': colobot})
        else:
            return jsonify({'success': False, 'error': 'Failed to save colobot'}), 500
            
    except Exception as e:
        print(f"Error updating colobot: {e}")
        return jsonify({'success': False, 'error': 'Failed to update colobot'}), 500

@app.route('/api/colobots/<colobot_id>', methods=['DELETE'])
def delete_colobot(colobot_id):
    """Delete a colobot"""
    try:
        actor, error = require_cilibit_user()
        if error:
            return error
        
        colobots = load_colobots()
        
        # Find and verify ownership
        colobot_index = None
        for i, c in enumerate(colobots):
            if c['id'] == colobot_id:
                if c['author'] == actor:
                    colobot_index = i
                    break
                else:
                    return jsonify({'success': False, 'error': 'Not authorized to delete this colobot'}), 403
        
        if colobot_index is None:
            return jsonify({'success': False, 'error': 'Colobot not found'}), 404
        
        # Delete the colobot
        colobots.pop(colobot_index)
        
        if save_colobots(colobots):
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to delete colobot'}), 500
            
    except Exception as e:
        print(f"Error deleting colobot: {e}")
        return jsonify({'success': False, 'error': 'Failed to delete colobot'}), 500

@app.route('/api/colobots/dates', methods=['GET'])
def get_colobot_dates():
    """Get all dates that have colobots (for calendar view)"""
    try:
        actor, error = require_cilibit_user()
        if error:
            return error
        colobots = load_colobots()
        
        # Extract unique dates
        dates = list(set(c.get('date') for c in colobots if c.get('date')))
        dates.sort()
        
        return jsonify({
            'success': True,
            'dates': dates,
            'count': len(dates)
        })
        
    except Exception as e:
        print(f"Error getting colobot dates: {e}")
        return jsonify({'success': False, 'error': 'Failed to fetch colobot dates'}), 500

@app.route('/api/colobots/today', methods=['GET'])
def get_today_colobots():
    """Get today's colobots"""
    try:
        actor, error = require_cilibit_user()
        if error:
            return error
        today = datetime.now().strftime('%Y-%m-%d')
        colobots = load_colobots()
        
        today_colobots = [c for c in colobots if c.get('date') == today]
        today_colobots.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        
        return jsonify({
            'success': True,
            'colobots': today_colobots,
            'count': len(today_colobots),
            'date': today
        })
        
    except Exception as e:
        print(f"Error getting today's colobots: {e}")
        return jsonify({'success': False, 'error': 'Failed to fetch today\'s colobots'}), 500

def _split_tags(value):
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value or '').replace(';', ',').split(',')
    return [str(item).strip()[:32] for item in raw if str(item).strip()][:12]


def _clean_ticket_payload(data, existing=None):
    existing = existing or {}
    return {
        'title': str(data.get('title') if data.get('title') is not None else existing.get('title', '')).strip()[:120],
        'kind': str(data.get('kind') if data.get('kind') is not None else existing.get('kind', 'other')).strip()[:32] or 'other',
        'ticketDate': str(data.get('ticketDate') if data.get('ticketDate') is not None else existing.get('ticketDate', '')).strip()[:32],
        'location': str(data.get('location') if data.get('location') is not None else existing.get('location', '')).strip()[:120],
        'notes': str(data.get('notes') if data.get('notes') is not None else existing.get('notes', '')).strip()[:2000],
        'tags': _split_tags(data.get('tags') if data.get('tags') is not None else existing.get('tags', [])),
    }


def _ticket_sort_key(ticket):
    return (ticket.get('ticketDate') or '0000-00-00', int(ticket.get('uploadedAt') or 0))


@app.route('/api/tickets', methods=['GET', 'POST'])
def tickets_collection():
    actor, error = require_cilibit_user()
    if error:
        return error

    if request.method == 'GET':
        tickets = sorted(load_tickets(), key=_ticket_sort_key, reverse=True)
        return jsonify({'success': True, 'tickets': tickets})

    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'PDF file is required'}), 400
    original_name = secure_filename(file.filename)
    if not original_name.lower().endswith('.pdf'):
        return jsonify({'success': False, 'error': 'Only PDF files are allowed'}), 400

    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size <= 0 or size > 40 * 1024 * 1024:
        return jsonify({'success': False, 'error': 'PDF file is too large'}), 413
    header = file.read(5)
    file.seek(0)
    if header != b'%PDF-':
        return jsonify({'success': False, 'error': 'File does not look like a PDF'}), 400

    payload = _clean_ticket_payload(request.form)
    if not payload['title']:
        payload['title'] = os.path.splitext(original_name)[0][:120] or 'ticket'
    ticket_id = uuid.uuid4().hex
    stored_name = f'{ticket_id}.pdf'
    os.makedirs(TICKET_UPLOAD_DIR, exist_ok=True)
    file.save(os.path.join(TICKET_UPLOAD_DIR, stored_name))

    ticket = {
        'id': ticket_id,
        **payload,
        'uploadedBy': actor,
        'uploadedAt': int(time.time() * 1000),
        'originalName': original_name,
        'storedName': stored_name,
        'size': size,
    }
    with CAMPFIRE_FILE_LOCK:
        tickets = load_tickets()
        tickets.append(ticket)
        if not save_tickets(tickets):
            return jsonify({'success': False, 'error': 'Failed to save ticket'}), 500
    publish_campfire_event(actor, 'activity', {'action': 'ticket', 'title': ticket['title']})
    return jsonify({'success': True, 'ticket': ticket})


@app.route('/api/tickets/<ticket_id>', methods=['PATCH', 'DELETE'])
def ticket_item(ticket_id):
    actor, error = require_cilibit_user()
    if error:
        return error
    with CAMPFIRE_FILE_LOCK:
        tickets = load_tickets()
        index = next((i for i, item in enumerate(tickets) if item.get('id') == ticket_id), -1)
        if index < 0:
            return jsonify({'success': False, 'error': 'Ticket not found'}), 404

        if request.method == 'DELETE':
            ticket = tickets.pop(index)
            if not save_tickets(tickets):
                return jsonify({'success': False, 'error': 'Failed to delete ticket'}), 500
            stored_name = secure_filename(ticket.get('storedName') or '')
            if stored_name:
                try:
                    os.remove(os.path.join(TICKET_UPLOAD_DIR, stored_name))
                except FileNotFoundError:
                    pass
            publish_campfire_event(actor, 'activity', {'action': 'ticket_delete', 'title': ticket.get('title', '')})
            return jsonify({'success': True})

        data = request.get_json(silent=True) or {}
        tickets[index].update(_clean_ticket_payload(data, tickets[index]))
        tickets[index]['updatedBy'] = actor
        tickets[index]['updatedAt'] = int(time.time() * 1000)
        if not save_tickets(tickets):
            return jsonify({'success': False, 'error': 'Failed to update ticket'}), 500
        return jsonify({'success': True, 'ticket': tickets[index]})


@app.route('/api/tickets/<ticket_id>/file', methods=['GET'])
def ticket_file(ticket_id):
    actor, error = require_cilibit_user()
    if error:
        return error
    ticket = next((item for item in load_tickets() if item.get('id') == ticket_id), None)
    if not ticket:
        return jsonify({'success': False, 'error': 'Ticket not found'}), 404
    stored_name = secure_filename(ticket.get('storedName') or '')
    if not stored_name:
        return jsonify({'success': False, 'error': 'Ticket file is missing'}), 404
    return send_from_directory(
        TICKET_UPLOAD_DIR,
        stored_name,
        mimetype='application/pdf',
        as_attachment=request.args.get('download') == '1',
        download_name=ticket.get('originalName') or stored_name,
    )


def _tmdb_config():
    return {
        'api_key': os.getenv('TMDB_API_KEY', '').strip(),
        'base_url': 'https://api.themoviedb.org/3',
        'image_base': 'https://image.tmdb.org/t/p',
    }


def _tmdb_image(path, size='w342'):
    if not path:
        return ''
    return f"{_tmdb_config()['image_base']}/{size}{path}"


def _tmdb_request(path, params=None):
    config = _tmdb_config()
    if not config['api_key']:
        raise RuntimeError('TMDB API key is not configured')
    query = dict(params or {})
    query['api_key'] = config['api_key']
    url = f"{config['base_url']}{path}?{urllib.parse.urlencode(query)}"
    request_obj = urllib.request.Request(url, headers={'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request_obj, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')[:300]
        raise RuntimeError(detail or f'TMDB request failed ({exc.code})') from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f'TMDB request failed: {exc.reason}') from exc


def _normalize_tmdb_result(item):
    media_type = item.get('media_type') or ('tv' if item.get('name') else 'movie')
    if media_type not in ('movie', 'tv'):
        return None
    title = item.get('title') if media_type == 'movie' else item.get('name')
    date_text = item.get('release_date') if media_type == 'movie' else item.get('first_air_date')
    return {
        'type': media_type,
        'tmdbId': item.get('id'),
        'title': title or '',
        'year': (date_text or '')[:4],
        'overview': item.get('overview') or '',
        'posterPath': item.get('poster_path') or '',
        'backdropPath': item.get('backdrop_path') or '',
        'posterUrl': _tmdb_image(item.get('poster_path')),
        'backdropUrl': _tmdb_image(item.get('backdrop_path'), 'w780'),
    }


def _normalize_tmdb_episode(item):
    return {
        'episodeNumber': item.get('episode_number'),
        'seasonNumber': item.get('season_number'),
        'name': item.get('name') or '',
        'overview': item.get('overview') or '',
        'airDate': item.get('air_date') or '',
        'stillUrl': _tmdb_image(item.get('still_path'), 'w300'),
    }


@app.route('/api/tv/search', methods=['GET'])
def tv_search():
    actor, error = require_cilibit_user()
    if error:
        return error
    query = (request.args.get('q') or '').strip()
    if len(query) < 2:
        return jsonify({'success': True, 'results': []})
    try:
        payload = _tmdb_request('/search/multi', {'query': query, 'include_adult': 'false', 'language': 'en-US'})
        results = [_normalize_tmdb_result(item) for item in payload.get('results', [])]
        return jsonify({'success': True, 'results': [item for item in results if item]})
    except RuntimeError as exc:
        return jsonify({'success': False, 'error': str(exc), 'needsConfig': 'TMDB API key' in str(exc)}), 503


@app.route('/api/tv/tmdb/<media_type>/<int:tmdb_id>', methods=['GET'])
def tv_tmdb_details(media_type, tmdb_id):
    actor, error = require_cilibit_user()
    if error:
        return error
    if media_type not in ('movie', 'tv'):
        return jsonify({'success': False, 'error': 'Unknown media type'}), 404
    try:
        payload = _tmdb_request(f'/{media_type}/{tmdb_id}', {'language': 'en-US'})
        details = _normalize_tmdb_result({**payload, 'media_type': media_type}) or {}
        if media_type == 'tv':
            details['numberOfSeasons'] = payload.get('number_of_seasons') or 0
            details['numberOfEpisodes'] = payload.get('number_of_episodes') or 0
            details['seasons'] = [
                {
                    'seasonNumber': season.get('season_number'),
                    'episodeCount': season.get('episode_count'),
                    'name': season.get('name') or '',
                    'posterUrl': _tmdb_image(season.get('poster_path')),
                }
                for season in payload.get('seasons', [])
            ]
        return jsonify({'success': True, 'details': details})
    except RuntimeError as exc:
        return jsonify({'success': False, 'error': str(exc), 'needsConfig': 'TMDB API key' in str(exc)}), 503


@app.route('/api/tv/tmdb/tv/<int:tmdb_id>/season/<int:season_number>', methods=['GET'])
def tv_tmdb_season_details(tmdb_id, season_number):
    actor, error = require_cilibit_user()
    if error:
        return error
    if season_number < 0 or season_number > 200:
        return jsonify({'success': False, 'error': 'Unknown season'}), 404
    try:
        payload = _tmdb_request(f'/tv/{tmdb_id}/season/{season_number}', {'language': 'en-US'})
        season = {
            'seasonNumber': payload.get('season_number'),
            'name': payload.get('name') or '',
            'overview': payload.get('overview') or '',
            'posterUrl': _tmdb_image(payload.get('poster_path')),
            'episodes': [_normalize_tmdb_episode(item) for item in payload.get('episodes', [])],
        }
        return jsonify({'success': True, 'season': season})
    except RuntimeError as exc:
        return jsonify({'success': False, 'error': str(exc), 'needsConfig': 'TMDB API key' in str(exc)}), 503


def _clean_watched_episodes(value):
    if not isinstance(value, dict):
        return {}
    cleaned = {}
    for season, episodes in value.items():
        try:
            season_number = int(season)
        except (TypeError, ValueError):
            continue
        if season_number < 0 or season_number > 200 or not isinstance(episodes, list):
            continue
        valid = []
        for episode in episodes:
            try:
                episode_number = int(episode)
            except (TypeError, ValueError):
                continue
            if 0 < episode_number <= 2000:
                valid.append(episode_number)
        if valid:
            cleaned[str(season_number)] = sorted(set(valid))
    return cleaned


def _clean_tv_entry(data, actor, existing=None):
    now = int(time.time() * 1000)
    entry = dict(existing or {})
    media_type = str(data.get('type') or entry.get('type') or 'tv')
    if media_type not in ('movie', 'tv'):
        media_type = 'tv'
    status = str(data.get('status') or entry.get('status') or 'watching')
    if status not in ('watching', 'planned', 'done', 'dropped'):
        status = 'watching'
    entry.update({
        'type': media_type,
        'tmdbId': int(data.get('tmdbId') or entry.get('tmdbId') or 0),
        'title': str(data.get('title') or entry.get('title') or '').strip()[:160],
        'year': str(data.get('year') or entry.get('year') or '')[:8],
        'overview': str(data.get('overview') or entry.get('overview') or '').strip()[:3000],
        'posterPath': str(data.get('posterPath') or entry.get('posterPath') or ''),
        'backdropPath': str(data.get('backdropPath') or entry.get('backdropPath') or ''),
        'posterUrl': str(data.get('posterUrl') or entry.get('posterUrl') or ''),
        'backdropUrl': str(data.get('backdropUrl') or entry.get('backdropUrl') or ''),
        'numberOfSeasons': max(0, int(data.get('numberOfSeasons') if data.get('numberOfSeasons') is not None else entry.get('numberOfSeasons', 0) or 0)),
        'numberOfEpisodes': max(0, int(data.get('numberOfEpisodes') if data.get('numberOfEpisodes') is not None else entry.get('numberOfEpisodes', 0) or 0)),
        'status': status,
        'season': max(0, int(data.get('season') if data.get('season') is not None else entry.get('season', 1) or 0)),
        'episode': max(0, int(data.get('episode') if data.get('episode') is not None else entry.get('episode', 0) or 0)),
        'watchedEpisodes': _clean_watched_episodes(data.get('watchedEpisodes') if data.get('watchedEpisodes') is not None else entry.get('watchedEpisodes', {})),
        'watched': bool(data.get('watched') if data.get('watched') is not None else entry.get('watched', False)),
        'watchedAt': str(data.get('watchedAt') or entry.get('watchedAt') or '')[:40],
        'lastWatchedAt': str(data.get('lastWatchedAt') or entry.get('lastWatchedAt') or '')[:40],
        'notes': str(data.get('notes') or entry.get('notes') or '').strip()[:2000],
        'updatedBy': actor,
        'updatedAt': now,
    })
    if not entry.get('id'):
        entry['id'] = uuid.uuid4().hex
        entry['addedBy'] = actor
        entry['addedAt'] = now
    if not entry['title']:
        entry['title'] = 'untitled'
    return entry


@app.route('/api/tv/catalog', methods=['GET', 'POST'])
def tv_catalog_collection():
    actor, error = require_cilibit_user()
    if error:
        return error
    if request.method == 'GET':
        catalog = sorted(load_tv_catalog(), key=lambda item: int(item.get('updatedAt') or item.get('addedAt') or 0), reverse=True)
        return jsonify({'success': True, 'catalog': catalog})
    data = request.get_json(silent=True) or {}
    entry = _clean_tv_entry(data, actor)
    with CAMPFIRE_FILE_LOCK:
        catalog = load_tv_catalog()
        existing_index = next((i for i, item in enumerate(catalog) if item.get('type') == entry['type'] and item.get('tmdbId') == entry['tmdbId'] and entry['tmdbId']), -1)
        if existing_index >= 0:
            entry = _clean_tv_entry(data, actor, catalog[existing_index])
            catalog[existing_index] = entry
        else:
            catalog.append(entry)
        if not save_tv_catalog(catalog):
            return jsonify({'success': False, 'error': 'Failed to save TV catalog'}), 500
    publish_campfire_event(actor, 'activity', {'action': 'tv', 'title': entry.get('title', '')})
    return jsonify({'success': True, 'entry': entry})


@app.route('/api/tv/catalog/<entry_id>', methods=['PATCH', 'DELETE'])
def tv_catalog_item(entry_id):
    actor, error = require_cilibit_user()
    if error:
        return error
    with CAMPFIRE_FILE_LOCK:
        catalog = load_tv_catalog()
        index = next((i for i, item in enumerate(catalog) if item.get('id') == entry_id), -1)
        if index < 0:
            return jsonify({'success': False, 'error': 'Catalog item not found'}), 404
        if request.method == 'DELETE':
            deleted = catalog.pop(index)
            if not save_tv_catalog(catalog):
                return jsonify({'success': False, 'error': 'Failed to delete catalog item'}), 500
            publish_campfire_event(actor, 'activity', {'action': 'tv_delete', 'title': deleted.get('title', '')})
            return jsonify({'success': True})
        data = request.get_json(silent=True) or {}
        catalog[index] = _clean_tv_entry(data, actor, catalog[index])
        if not save_tv_catalog(catalog):
            return jsonify({'success': False, 'error': 'Failed to update catalog item'}), 500
        return jsonify({'success': True, 'entry': catalog[index]})


def _clean_note(data, actor, existing=None):
    now = int(time.time() * 1000)
    note = dict(existing or {})
    note.update({
        'title': str(data.get('title') or note.get('title') or '').strip()[:120],
        'body': str(data.get('body') if data.get('body') is not None else note.get('body', ''))[:20000],
        'tags': _split_tags(data.get('tags') if data.get('tags') is not None else note.get('tags', [])),
        'pinned': bool(data.get('pinned') if data.get('pinned') is not None else note.get('pinned', False)),
        'updatedBy': actor,
        'updatedAt': now,
    })
    if not note.get('id'):
        note['id'] = uuid.uuid4().hex
        note['createdBy'] = actor
        note['createdAt'] = now
    if not note['title']:
        first_line = note['body'].strip().splitlines()[0] if note['body'].strip() else ''
        note['title'] = first_line[:60] or 'note'
    return note


@app.route('/api/notes', methods=['GET', 'POST'])
def notes_collection():
    actor, error = require_cilibit_user()
    if error:
        return error
    if request.method == 'GET':
        notes = sorted(load_notes(), key=lambda item: (bool(item.get('pinned')), int(item.get('updatedAt') or 0)), reverse=True)
        return jsonify({'success': True, 'notes': notes})
    data = request.get_json(silent=True) or {}
    note = _clean_note(data, actor)
    with CAMPFIRE_FILE_LOCK:
        notes = load_notes()
        notes.append(note)
        if not save_notes(notes):
            return jsonify({'success': False, 'error': 'Failed to save note'}), 500
    publish_campfire_event(actor, 'activity', {'action': 'note', 'title': note.get('title', '')})
    return jsonify({'success': True, 'note': note})


@app.route('/api/notes/<note_id>', methods=['PATCH', 'DELETE'])
def note_item(note_id):
    actor, error = require_cilibit_user()
    if error:
        return error
    with CAMPFIRE_FILE_LOCK:
        notes = load_notes()
        index = next((i for i, item in enumerate(notes) if item.get('id') == note_id), -1)
        if index < 0:
            return jsonify({'success': False, 'error': 'Note not found'}), 404
        if request.method == 'DELETE':
            deleted = notes.pop(index)
            if not save_notes(notes):
                return jsonify({'success': False, 'error': 'Failed to delete note'}), 500
            publish_campfire_event(actor, 'activity', {'action': 'note_delete', 'title': deleted.get('title', '')})
            return jsonify({'success': True})
        data = request.get_json(silent=True) or {}
        notes[index] = _clean_note(data, actor, notes[index])
        if not save_notes(notes):
            return jsonify({'success': False, 'error': 'Failed to update note'}), 500
        return jsonify({'success': True, 'note': notes[index]})

# Serve frontend files
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
        return "Static folder not configured", 404

    # Allow login and static assets without auth
    if path.startswith("static/") or path.startswith("uploads/"):
        pass
    elif path in ("login", "logout"):
        return send_from_directory(static_folder_path, 'login.html')
    else:
        auth_redirect = require_login()
        if auth_redirect:
            return auth_redirect

    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            return "index.html not found", 404

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/upload/image', methods=['POST'])
def upload_image():
    """Upload image file"""
    try:
        actor, error = require_cilibit_user()
        if error:
            return error
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        upload_type = request.form.get('type', 'cilibit')  # 'profile' or 'cilibit'
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'File type not allowed. Use PNG, JPG, JPEG, GIF, or WebP'}), 400
        
        # Check file size
        file.seek(0, 2)  # Seek to end
        file_size = file.tell()
        file.seek(0)  # Reset to beginning
        
        if file_size > MAX_FILE_SIZE:
            return jsonify({'success': False, 'error': f'File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB'}), 400
        
        # Generate unique filename
        file_extension = file.filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4().hex}.{file_extension}"
        
        # Determine upload directory and API URL
        if upload_type == 'profile':
            upload_dir = PROFILE_UPLOAD_DIR
            url_path = f'/api/image/profiles/{unique_filename}'
        else:  # cilibit
            upload_dir = CILIBIT_UPLOAD_DIR
            url_path = f'/api/image/cilibits/{unique_filename}'
        
        # Save file
        file_path = os.path.join(upload_dir, unique_filename)
        file.save(file_path)
        
        return jsonify({
            'success': True,
            'imageUrl': url_path,
            'filename': unique_filename,
            'originalName': file.filename,
            'size': file_size,
            'type': upload_type
        })
        
    except Exception as e:
        print(f"Error uploading image: {e}")
        return jsonify({'success': False, 'error': 'Upload failed'}), 500

@app.route('/static/uploads/<path:filename>')
def serve_uploaded_file(filename):
    """Serve uploaded files"""
    try:
        actor, error = require_cilibit_user()
        if error:
            return error
        response = send_from_directory(UPLOAD_DIR, filename)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        response.headers['Cache-Control'] = 'private, max-age=3600'
        return response
    except NotFound:
        return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        print(f"Error serving file {filename}: {e}")
        return jsonify({'error': 'File serving error'}), 500

@app.route('/static/<path:filename>')
def serve_static_file(filename):
    """Serve static files"""
    try:
        static_dir = os.path.join(os.path.dirname(__file__), 'static')
        response = send_from_directory(static_dir, filename)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response
    except Exception as e:
        print(f"Error serving static file {filename}: {e}")
        return jsonify({'error': 'Static file not found'}), 404

@app.route('/api/image/<path:filename>')
def get_image(filename):
    """Alternative endpoint to serve images via API"""
    try:
        actor, error = require_cilibit_user()
        if error:
            return error
        response = send_from_directory(UPLOAD_DIR, filename)
        response.headers['Cache-Control'] = 'private, max-age=3600'
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    except NotFound:
        return jsonify({'error': 'Image not found'}), 404
    except Exception as e:
        print(f"Error serving image {filename}: {e}")
        return jsonify({'error': 'Image serving error'}), 500

def _normalize_akademik_progress(progress_data):
    """Normalize akademik progress data into a dict with enver/irem lists."""
    if isinstance(progress_data, dict):
        enver_entries = progress_data.get('enver') if isinstance(progress_data.get('enver'), list) else []
        irem_entries = progress_data.get('irem') if isinstance(progress_data.get('irem'), list) else []
    elif isinstance(progress_data, list):
        enver_entries = progress_data
        irem_entries = []
    else:
        enver_entries = []
        irem_entries = []
    
    return {
        'enver': enver_entries,
        'irem': irem_entries
    }

@app.route('/api/akademik-progress', methods=['GET'])
def get_akademik_progress():
    """Get akademik manita progress entries for both users"""
    try:
        actor, error = require_cilibit_user()
        if error:
            return error
        
        if os.path.exists(AKADEMIK_PROGRESS_FILE):
            with open(AKADEMIK_PROGRESS_FILE, 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
        else:
            progress_data = []
        
        normalized = _normalize_akademik_progress(progress_data)
        
        return jsonify({
            'success': True,
            'lists': normalized,
            # Backward-compatible field for older clients
            'entries': normalized.get('enver', [])
        })
        
    except Exception as e:
        print(f"Error loading akademik progress: {e}")
        return jsonify({'success': False, 'error': 'Failed to load progress'}), 500


@app.route('/api/akademik-progress', methods=['POST'])
def update_akademik_progress():
    """Update akademik manita progress entries (enver or irem only)"""
    try:
        actor, error = require_cilibit_user()
        if error:
            return error
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        entries = data.get('entries', [])
        if not isinstance(entries, list):
            entries = []
        
        # Load existing data and normalize
        if os.path.exists(AKADEMIK_PROGRESS_FILE):
            with open(AKADEMIK_PROGRESS_FILE, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
        else:
            existing_data = []
        
        normalized = _normalize_akademik_progress(existing_data)
        normalized[actor] = entries
        
        # Save entries to file
        if not save_json_file(AKADEMIK_PROGRESS_FILE, normalized):
            return jsonify({'success': False, 'error': 'Failed to save progress'}), 500
        
        return jsonify({
            'success': True,
            'message': 'Progress updated successfully'
        })
        
    except Exception as e:
        print(f"Error updating akademik progress: {e}")
        return jsonify({'success': False, 'error': 'Failed to update progress'}), 500

if __name__ == '__main__':
    # Get configuration from environment variables
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')
    
    print("Starting Cilibit Flask server...")
    print(f"Data directory: {DATA_DIR}")
    print(f"Host: {host}")
    print(f"Port: {port}")
    print(f"Debug: {debug}")
    print(f"API Base URL: {os.getenv('API_URL', f'http://{host}:{port}')}")
    
    app.run(host=host, port=port, debug=debug)
