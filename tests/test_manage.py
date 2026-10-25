import io

import pytest
from fastapi.testclient import TestClient

from backend import manage
from backend.main import app
from tests.conftest import MEMBER_EMAIL, sign_in


def run(monkeypatch, argv, stdin="a-strong-password-1\n"):
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    return manage.main(argv)


def test_create_user_then_sign_in(db_state, monkeypatch, capsys):
    argv = ["create-user", "--email", "Cli@Example.com", "--name", "Cli User", "--role", "admin", "--password-stdin"]
    assert run(monkeypatch, argv) == 0
    assert "Created admin cli@example.com" in capsys.readouterr().out
    sign_in(TestClient(app), "cli@example.com", "a-strong-password-1")
    assert run(monkeypatch, argv) == 1  # duplicate


def test_create_user_rejects_weak_password(db_state, monkeypatch):
    assert run(monkeypatch, ["create-user", "--email", "a@b.c", "--password-stdin"], stdin="short\n") == 2


def test_set_password(db_state, monkeypatch):
    assert run(monkeypatch, ["set-password", "--email", MEMBER_EMAIL, "--password-stdin"], "member-new-pass-1\n") == 0
    sign_in(TestClient(app), MEMBER_EMAIL, "member-new-pass-1")
    assert run(monkeypatch, ["set-password", "--email", "nobody@x.y", "--password-stdin"]) == 1
    assert run(monkeypatch, ["set-password", "--email", MEMBER_EMAIL, "--password-stdin"], "short\n") == 2


def test_interactive_password_prompt_must_match(db_state, monkeypatch):
    answers = iter(["first-password-123", "second-password-123"])
    monkeypatch.setattr(manage.getpass, "getpass", lambda prompt: next(answers))
    with pytest.raises(SystemExit, match="did not match"):
        manage.main(["create-user", "--email", "a@b.c"])
