"""Tests for the bounded `.env` read in core.auth.

The `.env` is a 1Password local-env file: a FIFO that yields its contents only
once 1Password attaches as a writer. A blocking read waits forever when the app
is locked, so the read is bounded — and bounded at the *read*, not merely at a
wait on a worker thread, which used to leave that worker blocked for the life
of the process.
"""

import os
import threading
import time

from core import auth


def _attach_writer(path, text, delay=0.0):
    """Attach as a writer after `delay`, the way 1Password does."""
    def _writer():
        if delay:
            time.sleep(delay)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(text)
    thread = threading.Thread(target=_writer, daemon=True)
    thread.start()
    return thread


def test_read_env_text_reads_a_regular_file(tmp_path):
    path = tmp_path / '.env'
    path.write_text('HUE_BRIDGE_IP=192.0.2.1\n', encoding='utf-8')
    assert auth._read_env_text(str(path)) == 'HUE_BRIDGE_IP=192.0.2.1\n'


def test_read_env_text_returns_none_when_absent(tmp_path):
    assert auth._read_env_text(str(tmp_path / 'nope.env')) is None


def test_read_env_text_returns_none_for_an_empty_path():
    # find_dotenv() returns "" when it finds nothing; that must not be stat'ed.
    assert auth._read_env_text('') is None


def test_read_env_text_reads_a_fifo_once_a_writer_attaches(tmp_path):
    path = tmp_path / '.env'
    os.mkfifo(path)
    _attach_writer(path, 'HUE_BRIDGE_IP=192.0.2.9\n', delay=0.2)

    assert auth._read_env_text(str(path), timeout=5.0) == 'HUE_BRIDGE_IP=192.0.2.9\n'


def test_read_env_text_gives_up_when_no_writer_ever_attaches(tmp_path):
    """The locked-1Password case: must return, not hang."""
    path = tmp_path / '.env'
    os.mkfifo(path)

    started = time.monotonic()
    assert auth._read_env_text(str(path), timeout=0.3) is None
    assert time.monotonic() - started < 3.0


def test_read_env_text_leaves_no_thread_blocked_on_the_fifo(tmp_path):
    """The regression this replaces: the old loader abandoned a worker that
    stayed blocked on open() forever, leaking a thread and a FIFO reader."""
    path = tmp_path / '.env'
    os.mkfifo(path)
    before = threading.active_count()

    auth._read_env_text(str(path), timeout=0.3)

    assert threading.active_count() == before


def test_load_dotenv_safe_populates_the_environment(tmp_path, monkeypatch):
    path = tmp_path / '.env'
    path.write_text('HUE_BRIDGE_IP=192.0.2.2\n', encoding='utf-8')
    monkeypatch.setattr('dotenv.find_dotenv', lambda *a, **k: str(path))
    monkeypatch.delenv('HUE_BRIDGE_IP', raising=False)

    assert auth._load_dotenv_safe() is True
    assert os.environ['HUE_BRIDGE_IP'] == '192.0.2.2'


def test_load_dotenv_safe_does_not_override_an_existing_value(tmp_path, monkeypatch):
    """Matches load_dotenv()'s default: an explicit export still wins."""
    path = tmp_path / '.env'
    path.write_text('HUE_BRIDGE_IP=192.0.2.3\n', encoding='utf-8')
    monkeypatch.setattr('dotenv.find_dotenv', lambda *a, **k: str(path))
    monkeypatch.setenv('HUE_BRIDGE_IP', '192.0.2.4')

    assert auth._load_dotenv_safe() is True
    assert os.environ['HUE_BRIDGE_IP'] == '192.0.2.4'


def test_load_dotenv_safe_warns_and_reports_failure_on_timeout(tmp_path, monkeypatch, capsys):
    path = tmp_path / '.env'
    os.mkfifo(path)
    monkeypatch.setattr('dotenv.find_dotenv', lambda *a, **k: str(path))

    assert auth._load_dotenv_safe(timeout=0.3) is False
    assert '1Password' in capsys.readouterr().err
