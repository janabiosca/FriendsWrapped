"""Invitations accept any valid member id and store only the token hash."""
import hashlib
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import invite_spotify


def run(monkeypatch, capsys, *args):
    table = Mock()
    monkeypatch.setattr(invite_spotify.boto3, 'resource', lambda *a, **k: Mock(Table=lambda name: table))
    monkeypatch.setattr(sys, 'argv', ['invite', *args])
    invite_spotify.main()
    return table, capsys.readouterr().out.strip()


def test_any_valid_member_can_be_invited(monkeypatch, capsys):
    table, url = run(monkeypatch, capsys, '--user-id', 'alice', '--name', 'Alice',
                     '--base-url', 'https://connect.example/')
    token = url.split('invite=')[1]
    item = table.put_item.call_args.kwargs['Item']
    assert url.startswith('https://connect.example/connect?invite=')
    assert item['id'] == 'INVITE#' + hashlib.sha256(token.encode()).hexdigest()
    assert item['user_id'] == 'alice' and token not in str(item)


def test_invalid_member_id_is_rejected(monkeypatch, capsys):
    with pytest.raises(SystemExit) as error:
        run(monkeypatch, capsys, '--user-id', 'Alice Smith', '--name', 'Alice', '--base-url', 'https://x')
    assert error.value.code == 2
