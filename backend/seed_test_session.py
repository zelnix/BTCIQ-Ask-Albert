"""Seed a deterministic test user + auth session so the frontend testing agent
can bypass real Google OAuth (session-injection). Idempotent."""
import os, sys, uuid, datetime
sys.path.insert(0, os.path.dirname(__file__))
from config import users_col, auth_sessions_col  # noqa

TEST_EMAIL = 'albert.tester@example.com'
TEST_NAME = 'Albert Tester'
TEST_SUB = 'test-sub-albert-e2e-0001'
TEST_TOKEN = 'e2e_test_session_token_albert_0001'

now = datetime.datetime.utcnow()
users_col.update_one(
    {'google_sub': TEST_SUB},
    {'$set': {'email': TEST_EMAIL, 'name': TEST_NAME,
              'picture': 'https://ui-avatars.com/api/?name=Albert+Tester',
              'updated_at': now},
     '$setOnInsert': {'_id': str(uuid.uuid4()), 'google_sub': TEST_SUB,
                      'created_at': now}},
    upsert=True)
user = users_col.find_one({'google_sub': TEST_SUB})
uid = user['_id']

expires = now + datetime.timedelta(days=7)
auth_sessions_col.update_one(
    {'token': TEST_TOKEN},
    {'$set': {'user_id': uid, 'expires_at': expires, 'created_at': now},
     '$setOnInsert': {'_id': str(uuid.uuid4())}},
    upsert=True)

print('USER_ID=' + uid)
print('PID=u_' + uid)
print('SESSION_TOKEN=' + TEST_TOKEN)
print('EMAIL=' + TEST_EMAIL)
