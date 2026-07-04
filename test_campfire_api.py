import json
import io
import os
import tempfile
import unittest
import urllib.parse
from unittest import mock

os.environ.setdefault('CILIBIT_ENVER_PASSWORD', 'toor')
os.environ.setdefault('CILIBIT_IREM_PASSWORD', 'toor')
os.environ.setdefault('SECRET_KEY', 'test-secret-key')

from src import main


class CampfireApiTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = self.tempdir.name
        self.paths = {
            'CILIBITS_FILE': os.path.join(root, 'cilibits.json'),
            'USERS_FILE': os.path.join(root, 'users.json'),
            'SETTINGS_FILE': os.path.join(root, 'settings.json'),
            'CHATS_FILE': os.path.join(root, 'chats.json'),
            'MESSAGES_FILE': os.path.join(root, 'messages.json'),
            'CAMPFIRE_STATE_FILE': os.path.join(root, 'campfire_state.json'),
            'CAMPFIRE_ASSETS_FILE': os.path.join(root, 'campfire_assets.json'),
            'CAMPFIRE_READ_SESSIONS_FILE': os.path.join(root, 'campfire_read_sessions.json'),
            'CAMPFIRE_SHARED_FILE': os.path.join(root, 'campfire_shared.json'),
            'COLOBOTS_FILE': os.path.join(root, 'colobots.json'),
            'AKADEMIK_PROGRESS_FILE': os.path.join(root, 'akademik_progress.json'),
            'SPOTIFY_TOKENS_FILE': os.path.join(root, 'spotify_tokens.json'),
            'TICKETS_FILE': os.path.join(root, 'tickets.json'),
            'TV_CATALOG_FILE': os.path.join(root, 'tv_catalog.json'),
            'NOTES_FILE': os.path.join(root, 'notes.json'),
            'CILIBIT_UPLOAD_DIR': os.path.join(root, 'uploads', 'cilibits'),
            'PROFILE_UPLOAD_DIR': os.path.join(root, 'uploads', 'profiles'),
            'TICKET_UPLOAD_DIR': os.path.join(root, 'uploads', 'tickets'),
        }
        self.original_paths = {name: getattr(main, name) for name in self.paths}
        for name, path in self.paths.items():
            setattr(main, name, path)
        os.makedirs(main.CILIBIT_UPLOAD_DIR, exist_ok=True)
        os.makedirs(main.PROFILE_UPLOAD_DIR, exist_ok=True)
        os.makedirs(main.TICKET_UPLOAD_DIR, exist_ok=True)
        self.existing_cilibits = [{
            'id': 'old-1',
            'content': 'existing',
            'timestamp': 1,
            'author': 'enver',
            'parentId': None,
            'likes': ['irem'],
            'dislikes': [],
        }]
        main.save_json_file(main.CILIBITS_FILE, self.existing_cilibits)
        main.CAMPFIRE_EVENTS.clear()
        main.CAMPFIRE_EVENT_SEQUENCE = 0
        main.app.config.update(TESTING=True)
        self.client = main.app.test_client()

    def tearDown(self):
        for name, path in self.original_paths.items():
            setattr(main, name, path)
        self.tempdir.cleanup()

    def login(self, username='enver', password='toor'):
        return self.client.post('/api/session', json={'username': username, 'password': password})

    def test_session_and_private_state(self):
        self.assertEqual(self.client.get('/api/campfire/state/enver').status_code, 401)
        self.assertEqual(self.login().status_code, 200)
        response = self.client.put('/api/campfire/state/enver', json={
            'state': {'storage': {'campfire.mode.v1': 'night'}}
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.client.get('/api/campfire/state/enver').get_json()['state']['storage']['campfire.mode.v1'],
            'night',
        )
        self.assertEqual(self.client.put('/api/campfire/state/irem', json={'state': {}}).status_code, 403)

    def test_assets_reading_and_live_events_do_not_touch_cilibits(self):
        self.login()
        asset = {'id': 'a1', 'name': 'lamp', 'kind': 'deco', 'png': 'data:image/png;base64,AA=='}
        self.assertEqual(
            self.client.put('/api/campfire/assets', json={'assets': [asset]}).status_code,
            200,
        )
        self.assertEqual(self.client.get('/api/campfire/assets').get_json()['assets'][0]['id'], 'a1')

        sessions = [{'ts': '2026-06-13T10:00:00Z', 'date': 'Sat Jun 13 2026', 'duration': 600}]
        self.assertEqual(
            self.client.put('/api/campfire/read-sessions', json={'sessions': sessions}).status_code,
            200,
        )
        self.assertEqual(self.client.get('/api/campfire/read-sessions').get_json()['sessions'], sessions)

        event = self.client.post('/api/campfire/events', json={
            'type': 'state',
            'data': {'id': 'enver', 'x': 120},
        }).get_json()['event']
        self.assertEqual(event['from'], 'enver')

        other = main.app.test_client()
        other.post('/api/session', json={'username': 'irem', 'password': 'toor'})
        received = other.get('/api/campfire/events?after=0').get_json()['events']
        self.assertEqual(next(item for item in received if item['type'] == 'state')['seq'], event['seq'])

        with open(main.CILIBITS_FILE, encoding='utf-8') as handle:
            self.assertEqual(json.load(handle), self.existing_cilibits)

    def test_colobot_accepts_standalone_sighting_date(self):
        self.login()
        response = self.client.post('/api/colobots', json={
            'title': 'robin',
            'content': 'garden',
            'author': 'irem',
            'date': '2026-05-02',
            'tags': ['garden'],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['colobot']['date'], '2026-05-02')
        self.assertEqual(response.get_json()['colobot']['author'], 'enver')
        events = self.client.get('/api/campfire/events?after=0').get_json()['events']
        self.assertEqual(events[-1]['data']['action'], 'colobot')

    def test_upload_uses_portable_url_and_creations_publish_activity(self):
        self.login()
        upload = self.client.post('/api/upload/image', data={
            'file': (io.BytesIO(b'fake png'), 'photo.png'),
            'type': 'cilibit',
        }, content_type='multipart/form-data')
        self.assertEqual(upload.status_code, 200)
        self.assertTrue(upload.get_json()['imageUrl'].startswith('/api/image/cilibits/'))

        cilibit = self.client.post('/api/cilibits', json={
            'content': 'image post',
            'image': upload.get_json()['imageUrl'],
        })
        self.assertEqual(cilibit.status_code, 200)

        asset = {'id': 'a2', 'name': 'flower', 'kind': 'culubut', 'png': 'data:image/png;base64,AA=='}
        self.client.put('/api/campfire/assets', json={'assets': [asset]})
        events = self.client.get('/api/campfire/events?after=0').get_json()['events']
        self.assertEqual([event['data']['action'] for event in events], ['cilibit_image', 'studio_asset'])

    def test_shared_bootstrap_and_scoped_revisions(self):
        main.save_json_file(main.CAMPFIRE_STATE_FILE, {
            'enver': {'storage': {
                'campfire.props.v2': '{"fire":{"x":10}}',
                'cf.theme.v1': 'forest',
                'personal.key': 'kept-personal',
            }},
        })
        self.login()
        bootstrap = self.client.get('/api/campfire/bootstrap').get_json()
        self.assertEqual(
            bootstrap['shared']['scopes']['scene']['storage']['campfire.props.v2'],
            '{"fire":{"x":10}}',
        )
        self.assertEqual(bootstrap['shared']['scopes']['theme']['storage'], {})
        self.assertNotIn('personal.key', bootstrap['shared']['scopes']['scene']['storage'])

        scene = self.client.patch('/api/campfire/shared', json={
            'scope': 'scene',
            'storage': {'campfire.mode.v1': 'night', 'personal.key': 'ignored'},
        }).get_json()['shared']
        scene_revision = scene['scopes']['scene']['revision']
        themed = self.client.patch('/api/campfire/shared', json={
            'scope': 'theme',
            'storage': {'cf.theme.v1': 'moss'},
        })
        self.assertEqual(themed.status_code, 400)

        other = main.app.test_client()
        other.post('/api/session', json={'username': 'irem', 'password': 'toor'})
        events = other.get('/api/campfire/events?after=0').get_json()['events']
        self.assertEqual([event['type'] for event in events], ['shared'])

    def test_authenticated_writes_ignore_spoofed_identity(self):
        self.assertEqual(
            self.client.post('/api/cilibits', json={'content': 'blocked'}).status_code,
            401,
        )
        self.login()
        cilibit = self.client.post('/api/cilibits', json={
            'content': 'session owns this',
            'author': 'irem',
        }).get_json()['cilibit']
        self.assertEqual(cilibit['author'], 'enver')
        self.assertEqual(
            self.client.post('/api/profile/irem', json={'nickname': 'spoofed'}).status_code,
            403,
        )

        chat = self.client.post('/api/chats', json={
            'participants': ['irem', 'enver'],
        }).get_json()['chat']
        message = self.client.post(f"/api/chats/{chat['id']}/messages", json={
            'content': 'hello',
            'sender': 'irem',
        }).get_json()['message']
        self.assertEqual(message['sender'], 'enver')

    def test_akademik_writes_use_session_and_preserve_other_ledger(self):
        main.save_json_file(main.AKADEMIK_PROGRESS_FILE, {
            'enver': [{'text': 'old enver'}],
            'irem': [{'text': 'old irem'}],
        })
        self.login()
        response = self.client.post('/api/akademik-progress', json={
            'username': 'irem',
            'entries': [{'text': 'new enver'}],
        })
        self.assertEqual(response.status_code, 200)
        progress = self.client.get('/api/akademik-progress').get_json()['lists']
        self.assertEqual(progress['enver'], [{'text': 'new enver'}])
        self.assertEqual(progress['irem'], [{'text': 'old irem'}])


    def test_dm_read_and_delete_lifecycle(self):
        self.login()
        chat = self.client.post('/api/chats', json={
            'participants': ['enver', 'irem'],
        }).get_json()['chat']
        message = self.client.post(f"/api/chats/{chat['id']}/messages", json={
            'content': 'temporary lifecycle message',
        }).get_json()['message']

        other = main.app.test_client()
        other.post('/api/session', json={'username': 'irem', 'password': 'toor'})
        received = other.get(f"/api/chats/{chat['id']}/messages").get_json()['messages']
        self.assertTrue(received[0]['isRead'])
        self.assertEqual(other.post(f"/api/chats/{chat['id']}/mark-read").status_code, 200)
        self.assertEqual(
            other.delete(f"/api/chats/{chat['id']}/messages/{message['id']}").status_code,
            403,
        )
        self.assertEqual(
            self.client.delete(f"/api/chats/{chat['id']}/messages/{message['id']}").status_code,
            200,
        )

    def test_spotify_tokens_are_private_and_refreshed_server_side(self):
        self.assertEqual(self.client.get('/api/spotify/token').status_code, 401)
        self.login()
        self.assertEqual(self.client.get('/api/spotify/token').status_code, 404)
        main.save_json_file(main.SPOTIFY_TOKENS_FILE, {
            'enver': {
                'access_token': 'expired',
                'refresh_token': 'refresh-me',
                'expires_at': 1,
                'auth_mode': 'pkce',
            },
        })
        with mock.patch.dict(os.environ, {
            'SPOTIFY_CLIENT_ID': 'client',
            'SPOTIFY_CLIENT_SECRET': '',
        }), mock.patch.object(main, '_spotify_token_request', return_value={
            'access_token': 'fresh',
            'expires_in': 3600,
        }):
            response = self.client.get('/api/spotify/token')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['accessToken'], 'fresh')
        saved = main.load_json_file(main.SPOTIFY_TOKENS_FILE, {})
        self.assertEqual(saved['enver']['refresh_token'], 'refresh-me')

    def test_spotify_connect_uses_cilibit_session_and_configured_callback(self):
        self.login()
        with mock.patch.dict(os.environ, {
            'SPOTIFY_CLIENT_ID': 'client',
            'SPOTIFY_CLIENT_SECRET': '',
            'SPOTIFY_REDIRECT_URI': 'https://api.example.test/api/spotify/callback',
        }):
            response = self.client.get('/api/spotify/connect')
        self.assertEqual(response.status_code, 302)
        self.assertIn('accounts.spotify.com/authorize', response.location)
        self.assertIn('api.example.test%2Fapi%2Fspotify%2Fcallback', response.location)
        self.assertIn('code_challenge_method=S256', response.location)

    def test_spotify_callback_accepts_multiple_outstanding_states(self):
        self.login()
        env = {
            'SPOTIFY_CLIENT_ID': 'client',
            'SPOTIFY_CLIENT_SECRET': '',
            'SPOTIFY_REDIRECT_URI': 'https://api.example.test/api/spotify/callback',
        }
        with mock.patch.dict(os.environ, env):
            first = self.client.get('/api/spotify/connect?return_to=https://enverelectronics.com/cilibit/campfire.html')
            second = self.client.get('/api/spotify/connect?return_to=https://enverelectronics.com/cilibit/feed.html')
            first_state = urllib.parse.parse_qs(urllib.parse.urlparse(first.location).query)['state'][0]
            second_state = urllib.parse.parse_qs(urllib.parse.urlparse(second.location).query)['state'][0]
            with mock.patch.object(main, '_spotify_token_request', return_value={
                'access_token': 'first-token',
                'refresh_token': 'first-refresh',
                'expires_in': 3600,
            }):
                first_callback = self.client.get(
                    f'/api/spotify/callback?code=first-code&state={urllib.parse.quote(first_state)}'
                )
            self.assertEqual(first_callback.status_code, 302)
            self.assertIn('/cilibit/campfire.html', first_callback.location)

            with mock.patch.object(main, '_spotify_token_request', return_value={
                'access_token': 'second-token',
                'refresh_token': 'second-refresh',
                'expires_in': 3600,
            }):
                second_callback = self.client.get(
                    f'/api/spotify/callback?code=second-code&state={urllib.parse.quote(second_state)}'
                )
            self.assertEqual(second_callback.status_code, 302)
            self.assertIn('/cilibit/feed.html', second_callback.location)
            self.assertEqual(main.load_json_file(main.SPOTIFY_TOKENS_FILE, {})['enver']['access_token'], 'second-token')

    def test_tickets_pdf_lifecycle_is_authenticated(self):
        self.assertEqual(self.client.get('/api/tickets').status_code, 401)
        self.login()
        bad = self.client.post('/api/tickets', data={
            'file': (io.BytesIO(b'not a pdf'), 'ticket.txt'),
        }, content_type='multipart/form-data')
        self.assertEqual(bad.status_code, 400)

        created = self.client.post('/api/tickets', data={
            'file': (io.BytesIO(b'%PDF-1.4\n%%EOF'), 'museum.pdf'),
            'title': 'museum',
            'kind': 'museum',
            'ticketDate': '2026-06-01',
            'location': 'ankara',
            'tags': 'date, museum',
        }, content_type='multipart/form-data')
        self.assertEqual(created.status_code, 200)
        ticket = created.get_json()['ticket']
        self.assertEqual(ticket['uploadedBy'], 'enver')
        file_response = self.client.get(f"/api/tickets/{ticket['id']}/file")
        self.assertEqual(file_response.status_code, 200)
        file_response.close()

        updated = self.client.patch(f"/api/tickets/{ticket['id']}", json={'title': 'museum updated'}).get_json()['ticket']
        self.assertEqual(updated['title'], 'museum updated')
        self.assertEqual(self.client.delete(f"/api/tickets/{ticket['id']}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/tickets/{ticket['id']}/file").status_code, 404)

    def test_tv_search_and_catalog_lifecycle(self):
        self.login()
        with mock.patch.object(main, '_tmdb_request', return_value={
            'results': [{
                'media_type': 'tv',
                'id': 1399,
                'name': 'Game of Thrones',
                'first_air_date': '2011-04-17',
                'poster_path': '/poster.jpg',
                'overview': 'dragons',
            }]
        }):
            search = self.client.get('/api/tv/search?q=game').get_json()['results']
        self.assertEqual(search[0]['type'], 'tv')
        self.assertTrue(search[0]['posterUrl'].endswith('/w342/poster.jpg'))

        created = self.client.post('/api/tv/catalog', json={
            **search[0],
            'status': 'watching',
            'season': 1,
            'episode': 2,
        }).get_json()['entry']
        self.assertEqual(created['addedBy'], 'enver')
        self.assertEqual(created['episode'], 2)

        other = main.app.test_client()
        other.post('/api/session', json={'username': 'irem', 'password': 'toor'})
        updated = other.patch(f"/api/tv/catalog/{created['id']}", json={'episode': 3, 'watchedEpisodes': {'1': [1, 2, 3]}}).get_json()['entry']
        self.assertEqual(updated['updatedBy'], 'irem')
        self.assertEqual(updated['episode'], 3)
        self.assertEqual(updated['watchedEpisodes'], {'1': [1, 2, 3]})
        with mock.patch.object(main, '_tmdb_request', return_value={
            'season_number': 1,
            'name': 'Season 1',
            'episodes': [{'season_number': 1, 'episode_number': 1, 'name': 'Winter Is Coming'}],
        }):
            season = other.get('/api/tv/tmdb/tv/1399/season/1').get_json()['season']
        self.assertEqual(season['episodes'][0]['episodeNumber'], 1)
        self.assertEqual(other.delete(f"/api/tv/catalog/{created['id']}").status_code, 200)

    def test_notes_lifecycle_is_shared_and_authenticated(self):
        self.assertEqual(self.client.get('/api/notes').status_code, 401)
        self.login()
        created = self.client.post('/api/notes', json={
            'title': 'ticket ideas',
            'body': 'museum first',
            'tags': 'plan, museum',
            'pinned': True,
        }).get_json()['note']
        self.assertEqual(created['createdBy'], 'enver')
        self.assertEqual(created['tags'], ['plan', 'museum'])

        other = main.app.test_client()
        other.post('/api/session', json={'username': 'irem', 'password': 'toor'})
        notes = other.get('/api/notes').get_json()['notes']
        self.assertEqual(notes[0]['id'], created['id'])

        updated = other.patch(f"/api/notes/{created['id']}", json={
            'body': 'museum then train',
            'pinned': False,
        }).get_json()['note']
        self.assertEqual(updated['updatedBy'], 'irem')
        self.assertEqual(updated['body'], 'museum then train')
        self.assertFalse(updated['pinned'])
        self.assertEqual(other.delete(f"/api/notes/{created['id']}").status_code, 200)


if __name__ == '__main__':
    unittest.main()
