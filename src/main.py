import os
import sys
import json
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
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

# Upload directories
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
PROFILE_UPLOAD_DIR = os.path.join(UPLOAD_DIR, 'profiles')
CILIBIT_UPLOAD_DIR = os.path.join(UPLOAD_DIR, 'cilibits')
os.makedirs(PROFILE_UPLOAD_DIR, exist_ok=True)
os.makedirs(CILIBIT_UPLOAD_DIR, exist_ok=True)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB

# Data file paths
CILIBITS_FILE = os.path.join(DATA_DIR, 'cilibits.json')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
SETTINGS_FILE = os.path.join(DATA_DIR, 'settings.json')
CHATS_FILE = os.path.join(DATA_DIR, 'chats.json')
MESSAGES_FILE = os.path.join(DATA_DIR, 'messages.json')

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

@app.route('/api/chat-test', methods=['GET'])
def chat_test():
    """Test chat functionality"""
    try:
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
        username = request.args.get('username')
        if not username:
            return jsonify({'success': False, 'error': 'Username is required'}), 400
        
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
                for user in users:
                    if user['username'] == other_participant:
                        other_user_profile = {
                            'username': user['username'],
                            'nickname': user.get('displayName', user['username']),
                            'profilePicture': user.get('profilePicture', '')
                        }
                        break
                
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
        data = request.get_json()
        if not data or not data.get('participants') or len(data['participants']) < 2:
            return jsonify({'success': False, 'error': 'At least 2 participants are required'}), 400
        
        participants = sorted(data['participants'])  # Sort for consistent ordering
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
        username = request.args.get('username')
        if not username:
            return jsonify({'success': False, 'error': 'Username is required'}), 400
        
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
        for message in chat_messages:
            if message['sender'] != username:
                message['isRead'] = True
        
        save_messages(messages)
        
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
        data = request.get_json()
        if not data or not data.get('sender') or not data.get('content'):
            return jsonify({'success': False, 'error': 'Sender and content are required'}), 400
        
        chats = load_chats()
        messages = load_messages()
        
        # Verify chat exists and user is participant
        chat = None
        for c in chats:
            if c['id'] == chat_id:
                if data['sender'] in c['participants']:
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
            'sender': data['sender'],
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
        data = request.get_json()
        username = data.get('username')
        if not username:
            return jsonify({'success': False, 'error': 'Username is required'}), 400
        
        messages = load_messages()
        
        # Mark messages as read
        updated = False
        for message in messages:
            if message['chatId'] == chat_id and message['sender'] != username:
                if not message.get('isRead', False):
                    message['isRead'] = True
                    updated = True
        
        if updated and save_messages(messages):
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
        data = request.get_json()
        username = data.get('username')
        if not username:
            return jsonify({'success': False, 'error': 'Username is required'}), 400
        
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
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to save changes'}), 500
            
    except Exception as e:
        print(f"Error deleting message: {e}")
        return jsonify({'success': False, 'error': 'Failed to delete message'}), 500

@app.route('/api/cilibits', methods=['GET'])
def get_cilibits():
    """Get all cilibits"""
    try:
        # Ensure migration on first load
        migrate_cilibits_add_likes()
        
        cilibits = load_cilibits()
        
        # Filter out replies (only show top-level cilibits in main feed)
        top_level_cilibits = [c for c in cilibits if not c.get('parentId')]
        
        # Sort by timestamp (newest first)
        top_level_cilibits.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        
        return jsonify({
            'success': True,
            'topLevelCilibits': top_level_cilibits,
            'cilibits': top_level_cilibits,
            'pagination': {
                'currentPage': 1,
                'totalPages': 1,
                'totalItems': len(top_level_cilibits),
                'itemsPerPage': len(top_level_cilibits),
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

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/upload/image', methods=['POST'])
def upload_image():
    """Upload image file"""
    try:
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
        base_url = os.getenv('API_URL', 'https://api.enverelectronics.com')
        if upload_type == 'profile':
            upload_dir = PROFILE_UPLOAD_DIR
            url_path = f'{base_url}/api/image/profiles/{unique_filename}'
        else:  # cilibit
            upload_dir = CILIBIT_UPLOAD_DIR
            url_path = f'{base_url}/api/image/cilibits/{unique_filename}'
        
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
        # Ensure the upload directory exists
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        
        # Handle nested paths (profiles/xxx.jpg or cilibits/xxx.jpg)
        file_path = os.path.join(UPLOAD_DIR, filename)
        
        if os.path.exists(file_path):
            response = send_from_directory(UPLOAD_DIR, filename)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
            return response
        else:
            print(f"File not found: {file_path}")
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
        # Handle both profiles/xxx.jpg and cilibits/xxx.jpg
        file_path = os.path.join(UPLOAD_DIR, filename)
        
        if os.path.exists(file_path):
            # Get file extension to set correct MIME type
            ext = filename.split('.')[-1].lower()
            mime_types = {
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg', 
                'png': 'image/png',
                'gif': 'image/gif',
                'webp': 'image/webp'
            }
            
            with open(file_path, 'rb') as f:
                from flask import Response
                return Response(
                    f.read(),
                    mimetype=mime_types.get(ext, 'image/jpeg'),
                    headers={
                        'Cache-Control': 'public, max-age=3600',
                        'Access-Control-Allow-Origin': '*'
                    }
                )
        else:
            return jsonify({'error': 'Image not found'}), 404
            
    except Exception as e:
        print(f"Error serving image {filename}: {e}")
        return jsonify({'error': 'Image serving error'}), 500

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