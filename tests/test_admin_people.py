import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from quiz_bot import storage
from quiz_bot.admin_users import _BLOCKED_USERS_CACHE, is_user_blocked
from quiz_bot.loader import LOADED_TESTS
from quiz_bot.config import TESTS
from quiz_bot.webapp import create_webapp
from quiz_bot.web_admin_people import ensure_people_tables


class AdminPeopleTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        for item in (
            patch.object(storage, 'DATABASE_URL', None),
            patch.object(storage, 'db_connect', return_value=self.conn),
            patch('quiz_bot.admin_users.db_connect', return_value=self.conn),
            patch('quiz_bot.webapp.db_connect', return_value=self.conn),
            patch('quiz_bot.webapp._verified_telegram_data', return_value={'id': 1}),
            patch.dict('os.environ', {'ADMIN_IDS': '1'}),
            patch.dict(LOADED_TESTS, {'test_a': [{'question': 'Q'}], 'test_b': [{'question': 'B'}]}),
            patch.dict(TESTS, {'test_a': {'title':'A'}, 'test_b': {'title':'B'}}),
        ):
            item.start()
            self.addCleanup(item.stop)
        _BLOCKED_USERS_CACHE.clear()
        storage.init_db()
        ensure_people_tables()
        ensure_people_tables()
        for uid in range(1, 32):
            self.conn.execute('INSERT INTO users(user_id,first_name,profile_name) VALUES(?,?,?)', (uid, 'Student', f'App {uid}'))
        for test in ['test_a', 'test_b']:
            self.conn.execute("INSERT INTO attempts(user_id,test_id,mode,answered,correct) VALUES(2,?,'normal',2,1)", (test,))
            self.conn.execute('INSERT INTO all_time_errors(user_id,test_id,question_index,wrong_count) VALUES(2,?,0,1)', (test,))
            storage.set_favorite(2, test, 0, True)
        self.client = create_webapp().test_client()

    def tearDown(self):
        _BLOCKED_USERS_CACHE.clear()
        self.conn.close()

    def action(self, action, **values):
        return self.client.post('/api/admin/people/2/action', json={'action': action, **values})

    def test_paging_search_and_independent_counts(self):
        data = self.client.get('/api/admin/people').json
        self.assertEqual(data['total'], 31)
        self.assertEqual(len(data['items']), 25)
        self.assertTrue(data['has_more'])
        self.assertEqual(len(self.client.get('/api/admin/people?page=1').json['items']), 6)
        user = self.client.get('/api/admin/people?search=App+2').json['items']
        student = next(row for row in user if row['user_id'] == 2)
        self.assertEqual(student['attempts_count'], 2)
        self.assertEqual(student['active_errors'], 2)
        self.assertEqual(student['accuracy'], 50)
        detail = self.client.get('/api/admin/people/2').json
        self.assertEqual(detail['stats']['answered'], 4)
        self.assertEqual(detail['user']['name'], 'App 2')
        legacy = self.client.get('/api/admin/users').json['items']
        self.assertEqual(next(row for row in legacy if row['user_id']==2)['answered_count'], 4)

    def test_error_total_not_truncated(self):
        for index in range(1, 40):
            self.conn.execute("INSERT INTO all_time_errors(user_id,test_id,question_index,wrong_count) VALUES(2,'test_a',?,1)", (index,))
        data = self.client.get('/api/admin/people/2').json
        self.assertEqual(data['stats']['active_errors'], 41)
        self.assertEqual(len(data['errors']), 25)
        self.assertEqual(len(self.client.get('/api/admin/people/2?page=1').json['errors']), 16)
        self.assertEqual(self.client.get('/api/admin/user/detail?target_user_id=2').json['stats']['active_errors'], 41)

    def test_activity_filter_and_test_filter(self):
        old = str(datetime.now() - timedelta(days=40))
        self.conn.execute('UPDATE users SET last_seen_at=?, first_seen_at=? WHERE user_id=2', (old,old))
        self.assertNotIn(2, [row['user_id'] for row in self.client.get('/api/admin/people?tab=active7').json['items']])
        self.assertEqual(self.client.get('/api/admin/people?tab=inactive30').json['total'],1)
        self.assertEqual(self.client.get('/api/admin/people/2?test_id=test_a').json['stats']['attempts_total'],1)
        self.assertEqual(self.client.get('/api/admin/people/2?days=10').status_code,400)

    def test_access_notes_and_authorization(self):
        self.assertEqual(self.action('grant',test_id='test_a').status_code,200)
        self.assertEqual(storage.list_user_test_access(2),['test_a'])
        self.assertEqual(self.action('note',text='Private note').status_code,200)
        self.assertEqual(self.client.get('/api/admin/people/2').json['note']['note'],'Private note')
        self.assertEqual(self.action('revoke',test_id='test_a').status_code,200)
        self.assertEqual(storage.list_user_test_access(2),[])
        self.assertEqual(self.action('grant',test_id='missing').status_code,400)
        with patch('quiz_bot.webapp._verified_telegram_data',return_value={'id':3}):
            self.assertEqual(self.client.get('/api/admin/people/2').status_code,403)
            self.assertEqual(self.action('note',text='bad').status_code,403)

    def test_timed_block_is_enforced_and_expires(self):
        self.assertEqual(self.action('block',reason='Test',days=1).status_code,200)
        self.assertTrue(is_user_blocked(2))
        with patch('quiz_bot.webapp._verified_telegram_data',return_value={'id':2}):
            self.assertEqual(self.client.get('/api/user/state').status_code,403)
        self.conn.execute('UPDATE blocked_users SET blocked_until=? WHERE user_id=2', (str(datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(seconds=1)),))
        _BLOCKED_USERS_CACHE.clear()
        self.assertFalse(is_user_blocked(2))
        self.assertFalse(self.client.get('/api/admin/people/2').json['user']['is_blocked'])
        self.assertEqual(self.client.post('/api/admin/people/1/action',json={'action':'block','reason':'No','days':1}).status_code,400)

    def test_targeted_reset_preserves_other_data_and_marks_devices(self):
        self.assertEqual(self.action('reset',kind='errors',test_id='test_a',confirmed=True).status_code,200)
        self.assertEqual(storage.get_all_time_error_indices(2,'test_a'),[])
        self.assertEqual(storage.get_all_time_error_indices(2,'test_b'),[0])
        self.assertEqual(storage.favorite_count(2,'test_a'),1)
        self.assertEqual(self.action('reset',kind='all',test_id='test_b',confirmed=True).status_code,200)
        detail = self.client.get('/api/admin/people/2').json
        self.assertEqual(detail['stats']['attempts_total'],1)
        self.assertEqual(storage.favorite_count(2,'test_b'),0)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM user_progress_resets WHERE user_id=2').fetchone()[0],2)
        self.assertEqual(self.action('reset',kind='all').status_code,400)
        self.assertEqual(self.action('reset',kind='unknown',confirmed=True).status_code,400)

    def test_message_failure_is_not_reported_as_success(self):
        with patch('quiz_bot.web_admin_people.get_bot_token',return_value=''):
            result = self.action('message',text='Test')
        self.assertEqual(result.status_code,502)
        self.assertFalse(result.json['success'])
        self.assertEqual(self.client.get('/api/admin/people/2').json['messages'][0]['status'],'failed')

    def test_message_success_records_sender(self):
        bot=MagicMock()
        bot.__aenter__=AsyncMock(return_value=bot)
        bot.__aexit__=AsyncMock(return_value=False)
        bot.send_message=AsyncMock()
        with patch('quiz_bot.web_admin_people.get_bot_token',return_value='test'), patch('telegram.Bot',return_value=bot):
            result=self.action('message',text='Hello')
        self.assertEqual(result.status_code,200)
        bot.send_message.assert_awaited_once_with(chat_id=2,text='Hello')
        record=self.client.get('/api/admin/people/2').json['messages'][0]
        self.assertEqual(record['status'],'sent')
        self.assertEqual(record['sent_by'],1)

    def test_private_test_access_grant_and_revoke_are_effective(self):
        storage.set_test_access_setting('test_a','private')
        with patch('quiz_bot.webapp._verified_telegram_data',return_value={'id':3}):
            self.assertFalse(self.client.get('/api/tests/test_a/access').json['allowed'])
            self.assertEqual(self.client.get('/api/tests/test_a').status_code,403)
        storage.grant_user_test_access(3,'test_a','admin',1)
        with patch('quiz_bot.webapp._verified_telegram_data',return_value={'id':3}):
            self.assertTrue(self.client.get('/api/tests/test_a/access').json['allowed'])
            self.assertEqual(self.client.get('/api/tests/test_a').status_code,200)
        storage.revoke_user_test_access(3,'test_a')
        with patch('quiz_bot.webapp._verified_telegram_data',return_value={'id':3}):
            self.assertFalse(self.client.get('/api/tests/test_a/access').json['allowed'])
            self.assertEqual(self.client.get('/api/tests/test_a').status_code,403)


if __name__ == '__main__':
    unittest.main()
