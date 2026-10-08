"""Run the small Render demo web/worker pair; stop both if either exits."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def main():
    if not os.environ.get('CELERY_BROKER_URL'):
        raise SystemExit('CELERY_BROKER_URL is required for the Render web/worker service')
    if os.environ.get('LIBRARY_BOOTSTRAPPED') != '1':
        # Some hosting launchers override ENTRYPOINT as well as CMD.
        os.execv('/entrypoint.sh', ['/entrypoint.sh', sys.executable, str(Path(__file__).resolve())])
    children = []
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    result = 0
    try:
        commands = [
            ['celery', '-A', 'library', 'worker', '--loglevel=INFO', '--pool=solo',
             '--concurrency=1', '--queues=events', '--without-gossip', '--without-mingle'],
            ['gunicorn', 'library.wsgi:application', '--workers=1', '--timeout=120',
             '--access-logfile=-', '--error-logfile=-', '--capture-output',
             '--bind', '0.0.0.0:' + os.environ.get('PORT', '8000')],
        ]
        for command in commands:
            children.append(subprocess.Popen(command, start_new_session=True))
        while not stopping:
            if any(child.poll() is not None for child in children):
                print('A Render child process exited; stopping the service', flush=True)
                result = 1
                break
            time.sleep(0.2)
    finally:
        for child in children:
            try:
                # Also stop workers left behind if their process-group leader exited.
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 20
        for child in children:
            try:
                child.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
    return result


if __name__ == '__main__':
    sys.exit(main())
