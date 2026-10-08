"""Start the baked Render command with seed and a hard 512 MiB container limit."""
import argparse
import json
import re
from http.cookiejar import CookieJar
from urllib.parse import urlencode
import subprocess
import time
import uuid
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--compose-file')
parser.add_argument('--project-name')
parser.add_argument('--port', type=int, default=18448)
parser.add_argument('--cpus', default='0.1')
args = parser.parse_args()
compose = ['docker', 'compose']
if args.compose_file:
    compose += ['-f', args.compose_file]
if args.project_name:
    compose += ['-p', args.project_name]


def output(command):
    return subprocess.check_output(command, text=True).strip()


web_id = output(compose + ['ps', '-q', 'web'])
web = json.loads(output(['docker', 'inspect', web_id]))[0]
network = next(iter(web['NetworkSettings']['Networks']))
name = (args.project_name or 'library-ci') + '-render-free'
command = ['docker', 'run', '-d', '--name', name, '--network', network,
           '--memory', '512m', '--memory-swap', '512m', '--cpus', args.cpus,
           '--entrypoint', 'python', '-p', f'127.0.0.1:{args.port}:10000']
for item in web['Config']['Env']:
    if item.split('=', 1)[0] not in ('DJANGO_SEED', 'PORT', 'CELERY_TASK_ALWAYS_EAGER', 'LIBRARY_BOOTSTRAPPED'):
        command += ['-e', item]
command += ['-e', 'DJANGO_SEED=true', '-e', 'RENDER=true', '-e', 'PORT=10000', web['Image'],
            '/app/scripts/render_start.py']
try:
    subprocess.run(command, check=True)
    for attempt in range(600):
        state = json.loads(output(['docker', 'inspect', name]))[0]['State']
        if not state['Running']:
            raise RuntimeError(f'Render container exited: {state}')
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/api/schema/', timeout=2) as response:
                if response.status == 200:
                    break
        except (OSError, TimeoutError):
            time.sleep(1)
    else:
        raise RuntimeError('Render seed/web startup timed out')
    for path in ('/api/docs/', '/api/schema/', '/api/v1/'):
        with urllib.request.urlopen(f'http://127.0.0.1:{args.port}{path}', timeout=10) as response:
            assert response.status == 200
    subprocess.run(['docker', 'exec', name, 'python', 'manage.py', 'shell', '-c',
        'from book.models import Book, BookEmbedding; '
        'from book.embeddings import MODEL_REVISION; '
        'assert Book.objects.exists(); '
        'assert BookEmbedding.objects.filter(model_revision=MODEL_REVISION).count() == Book.objects.count(); '
        'print("PASS: real seed with int8 vectors under 512 MiB")'], check=True)
    subprocess.run(['docker', 'exec', name, 'python', 'manage.py', 'smoke_test_tracking', '--base-url', 'http://127.0.0.1:10000'], check=True)
    # Generate a vector inside the serving Gunicorn process, not only in a CLI.
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    base = f'http://127.0.0.1:{args.port}'
    opener.addheaders = [('X-Forwarded-Proto', 'https'), ('Origin', f'https://127.0.0.1:{args.port}')]
    def form(path, fields=None):
        with opener.open(base + path, timeout=120) as response:
            html = response.read().decode()
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html).group(1)
        if fields is not None:
            data = urlencode(dict(fields, csrfmiddlewaretoken=token)).encode()
            with opener.open(base + path, data=data, timeout=120) as response:
                return response.read().decode()
    form('/authentication/login/', {'email': 'librarian@library.com', 'password': 'admin123password'})
    book_name = 'KAN-47 memory ' + uuid.uuid4().hex[:8]
    html = form('/book/create/', {'name': book_name, 'description': 'Українська книга', 'count': 2})
    assert 'Could not generate' not in html
    subprocess.run(['docker', 'exec', name, 'python', 'manage.py', 'shell', '-c',
        'from book.models import Book; '
        f'b=Book.objects.get(name={book_name!r}); '
        'assert len(b.embedding.vector) == 384; '
        'print("PASS: HTTP book creation with real int8 inference at 512 MiB")'], check=True)
    print('Container peak bytes: ' + output(['docker', 'exec', name, 'cat', '/sys/fs/cgroup/memory.peak']))
    print(output(['docker', 'stats', '--no-stream', '--format', '{{.MemUsage}}', name]))
    subprocess.run(['docker', 'stop', '--time', '25', name], check=True)
    state = json.loads(output(['docker', 'inspect', name]))[0]['State']
    assert not state['OOMKilled'] and state['ExitCode'] == 0, state
    print('PASS: Render seed, HTTP, embeddings, async events and graceful shutdown at 512 MiB')
finally:
    subprocess.run(['docker', 'logs', '--tail', '40', name], check=False)
    subprocess.run(['docker', 'rm', '-f', name], check=False)
