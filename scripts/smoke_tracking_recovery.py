"""Disposable Compose-stack check: queued events survive worker/broker restart."""
import argparse
import subprocess
import uuid

parser = argparse.ArgumentParser()
parser.add_argument('--compose-file')
parser.add_argument('--project-name')
args = parser.parse_args()
compose = ['docker', 'compose']
if args.compose_file:
    compose += ['-f', args.compose_file]
if args.project_name:
    compose += ['-p', args.project_name]


def run(*command):
    subprocess.run(compose + list(command), check=True)


def shell(code):
    run('exec', '-T', 'web', 'python', 'manage.py', 'shell', '-c', code)


identity = str(uuid.uuid4())
run('stop', 'worker')
try:
    shell(f"""
from django.utils import timezone
from events.models import UserEvent
from events.services import publish_event
publish_event({{
    'id': {identity!r}, 'user_id': 2147483647, 'event_type': 'login',
    'source': 'server', 'book_id': None, 'path': '',
    'properties': {{'check': 'worker_restart_smoke'}},
    'occurred_at': timezone.now().isoformat(),
}})
assert not UserEvent.objects.filter(pk={identity!r}).exists(), 'Worker must be the only event writer'
print('PASS: queued while worker is stopped; not synchronously stored')
""")
    run('restart', 'redis')
finally:
    run('start', 'worker')
shell(f"""
import time
from events.models import UserEvent
for attempt in range(300):
    if UserEvent.objects.filter(pk={identity!r}).exists():
        break
    time.sleep(0.1)
else:
    raise RuntimeError('Queued event did not survive worker/Redis restart')
event = UserEvent.objects.get(pk={identity!r})
assert event.properties == {{'check': 'worker_restart_smoke'}}
assert event.user_id is None
UserEvent.objects.filter(pk={identity!r}).delete()
print('PASS: event persisted after worker/Redis restart')
""")
