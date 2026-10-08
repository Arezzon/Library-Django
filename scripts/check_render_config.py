"""Validate the deployment contract used by the free demo."""
from pathlib import Path
import yaml

config = yaml.safe_load(Path('render.yaml').read_text())
services = {service['name']: service for service in config['services']}
web = services['library-django']
queue = services['library-queue']
assert len(services) == 2, 'Free deployment must not provision a paid worker'
assert web['type'] == 'web' and web['runtime'] == 'docker' and web['plan'] == 'free'
assert web['dockerCommand'] == 'python /app/scripts/render_start.py'
assert 'repo' not in web, 'Blueprint must deploy the user-selected repository'
assert queue['type'] == 'keyvalue' and queue['plan'] == 'free'
assert queue['maxmemoryPolicy'] == 'noeviction' and queue['ipAllowList'] == []
env = {item['key']: item for item in web['envVars']}
assert env['CELERY_BROKER_URL']['fromService'] == {
    'type': 'keyvalue', 'name': 'library-queue', 'property': 'connectionString'}
assert env['DJANGO_SEED']['value'] == 'true', 'Seed and embeddings must remain enabled'
assert env['DEBUG']['value'] == 'False'
assert len(config['databases']) == 1
assert config['databases'][0]['plan'] == 'free'
assert web['region'] == queue['region'] == config['databases'][0]['region']
for key, prop in [('DB_HOST', 'host'), ('DB_PORT', 'port'), ('DB_USER', 'user'),
                  ('DB_PASSWORD', 'password'), ('DB_NAME', 'database')]:
    assert env[key]['fromDatabase'] == {'name': 'library-db', 'property': prop}
print('PASS: free web/queue/database deployment contract')
