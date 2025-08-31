import os
import sys
import json
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))
app.config['SECRET_KEY'] = 'asdf#FGSgvasgf$5$WGT'

# Enable CORS for all routes
cors_origins = os.getenv('CORS_ORIGINS', '*').split(',') if os.getenv('CORS_ORIGINS') else ['*']
CORS(app, origins=cors_origins)

# Data directory
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

# Data file paths
CILIBITS_FILE = os.path.join(DATA_DIR, 'cilibits.json')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
SETTINGS_FILE = os.path.join(DATA_DIR, 'settings.json')

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
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
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

@app.route('/api/users', methods=['GET'])
@app.route('/users', methods=['GET'])  # Add both routes for compatibility
def get_users():
    """Get all users"""
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

@app.route('/api/cilibits', methods=['GET'])
def get_cilibits():
    """Get all cilibits"""
    try:
        # Ensure migration on first load
        migrate_cilibits_add_likes()
        
        cilibits = load_cilibits()
        
        # Sort by timestamp (newest first)
        cilibits.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        
        return jsonify({
            'success': True,
            'topLevelCilibits': cilibits,
            'cilibits': cilibits,
            'pagination': {
                'currentPage': 1,
                'totalPages': 1,
                'totalItems': len(cilibits),
                'itemsPerPage': len(cilibits),
                'hasNext': False,
                'hasPrev': False
            }
        })
    except Exception as e:
        print(f"Error getting cilibits: {e}")
        return jsonify({'success': False, 'error': 'Failed to fetch cilibits'}), 500

@app.route('/api/cilibits', methods=['POST'])
def create_cilibit():
    """Create a new cilibit"""
    try:
        data = request.get_json()
        if not data or not data.get('content') or not data.get('author'):
            return jsonify({'success': False, 'error': 'Content and author are required'}), 400
        
        cilibits = load_cilibits()
        
        # Create new cilibit
        new_cilibit = {
            'id': str(int(datetime.now().timestamp() * 1000)),
            'content': data['content'],
            'timestamp': int(datetime.now().timestamp() * 1000),
            'author': data['author'],
            'parentId': data.get('parentId'),
            'image': data.get('image'),
            'isGif': data.get('isGif', False),
            'isCulubut': data.get('isCulubut', False),
            'likes': [],
            'dislikes': []
        }
        
        cilibits.append(new_cilibit)
        
        if save_cilibits(cilibits):
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
        data = request.get_json()
        if not data or not data.get('id') or not data.get('username'):
            return jsonify({'success': False, 'error': 'Cilibit ID and username are required'}), 400
        
        cilibits = load_cilibits()
        cilibit_id = data['id']
        username = data['username']
        
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
        data = request.get_json()
        if not data or not data.get('id') or not data.get('username'):
            return jsonify({'success': False, 'error': 'Cilibit ID and username are required'}), 400
        
        cilibits = load_cilibits()
        cilibit_id = data['id']
        username = data['username']
        
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
        data = request.get_json()
        if not data or not data.get('id') or not data.get('username'):
            return jsonify({'success': False, 'error': 'Cilibit ID and username are required'}), 400
        
        cilibits = load_cilibits()
        cilibit_id = data['id']
        username = data['username']
        
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
        data = request.get_json()
        if not data or not data.get('title') or not data.get('content') or not data.get('author'):
            return jsonify({'success': False, 'error': 'Title, content, and author are required'}), 400
        
        colobots = load_colobots()
        
        # Get today's date
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Check if user is trying to create colobot for today only
        colobot_date = data.get('date', today)
        if colobot_date != today:
            return jsonify({'success': False, 'error': 'Colobots can only be created for today'}), 400
        
        # Create new colobot
        new_colobot = {
            'id': str(int(datetime.now().timestamp() * 1000)),
            'title': data['title'],
            'content': data['content'],
            'birdImage': data.get('birdImage', ''),
            'author': data['author'],
            'date': today,
            'timestamp': int(datetime.now().timestamp() * 1000),
            'tags': data.get('tags', [])
        }
        
        colobots.append(new_colobot)
        
        if save_colobots(colobots):
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
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        colobots = load_colobots()
        
        # Find the colobot
        colobot_index = None
        for i, c in enumerate(colobots):
            if c['id'] == colobot_id:
                # Check if user is author
                if c['author'] != data.get('username'):
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
        data = request.get_json()
        username = data.get('username') if data else None
        
        if not username:
            return jsonify({'success': False, 'error': 'Username required'}), 400
        
        colobots = load_colobots()
        
        # Find and verify ownership
        colobot_index = None
        for i, c in enumerate(colobots):
            if c['id'] == colobot_id:
                if c['author'] == username or username == 'admin':
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

# Serve frontend files
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
        return "Static folder not configured", 404

    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            return "index.html not found", 404

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