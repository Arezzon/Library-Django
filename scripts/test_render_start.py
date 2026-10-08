"""Exercise service lifecycle with real child processes and signals."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import importlib.util

SCRIPT = Path(__file__).resolve().with_name('render_start.py')


class RenderLifecycleTests(unittest.TestCase):
    def run_service(self, failing=False, kill=False):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for name in ('celery', 'gunicorn'):
                executable = folder / name
                executable.write_text(
                    '#!' + sys.executable + '\n'
                    'import os, signal, time\n'
                    'from pathlib import Path\n'
                    f'path = Path({str(folder / name)!r} + ".started")\n'
                    'path.write_text(str(os.getpid()))\n'
                    'signal.signal(signal.SIGTERM, lambda *args: exit(0))\n'
                    + ('time.sleep(0.4)\nexit(7)\n' if failing and name == 'celery'
                       else 'while True: time.sleep(0.1)\n'))
                executable.chmod(0o755)
            env = dict(os.environ, PATH=directory + ':' + os.environ['PATH'],
                       CELERY_BROKER_URL='redis://example:6379/0', LIBRARY_BOOTSTRAPPED='1')
            process = subprocess.Popen([sys.executable, str(SCRIPT)], env=env)
            pids = []
            try:
                deadline = time.monotonic() + 5
                while not all((folder / (name + '.started')).exists()
                              for name in ('celery', 'gunicorn')):
                    if time.monotonic() > deadline:
                        self.fail('Children did not start')
                    time.sleep(0.02)
                pids = [int((folder / (name + '.started')).read_text())
                        for name in ('celery', 'gunicorn')]
                if kill:
                    process.send_signal(signal.SIGTERM)
                self.assertEqual(process.wait(timeout=5), 1 if failing else 0)
                for pid in pids:
                    with self.assertRaises(ProcessLookupError):
                        os.kill(pid, 0)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=25)

    def test_child_failure_stops_sibling_and_exits_nonzero(self):
        self.run_service(failing=True)

    def test_sigterm_stops_both_children(self):
        self.run_service(kill=True)

    def test_missing_broker_fails_before_starting_children(self):
        env = dict(os.environ)
        env.pop('CELERY_BROKER_URL', None)
        result = subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'CELERY_BROKER_URL is required', result.stderr)

    def test_direct_start_enters_database_bootstrap_before_starting_children(self):
        spec = importlib.util.spec_from_file_location('render_supervisor', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        env = dict(os.environ, CELERY_BROKER_URL='redis://example:6379/0')
        env.pop('LIBRARY_BOOTSTRAPPED', None)
        with patch.dict(os.environ, env, clear=True), patch.object(module.os, 'execv', side_effect=RuntimeError('exec replaced process')) as execute:
            with self.assertRaisesRegex(RuntimeError, 'exec replaced process'):
                module.main()
        execute.assert_called_once_with('/entrypoint.sh', ['/entrypoint.sh', sys.executable, str(SCRIPT)])
