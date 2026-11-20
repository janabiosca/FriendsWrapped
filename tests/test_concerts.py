"""Publish only complete snapshots and enforce group authorization for concert data."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import boto3
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import concerts
import dashboard
from test_spotify_connect import setup
from test_dashboard import allow, request, userinfo
from test_ticketmaster import event

NOW = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)


@pytest.fixture
def discovery(setup, monkeypatch):
    monkeypatch.setenv('TICKETMASTER_SECRET', 'sfw-test/ticketmaster')
    boto3.client('secretsmanager').create_secret(Name='sfw-test/ticketmaster', SecretString=json.dumps({'api_key': 'fake-key'}))
    monkeypatch.setattr(concerts, 'preferences', lambda *args: {'malmo040': {'name': 'Malmö 040', 'user_ids': {'jana'}}})
    monkeypatch.setattr(concerts.ticketmaster, 'artist_events', lambda *args: [event()])


def test_one_event_is_published_only_after_complete_scan(discovery):
    result = concerts.collect('friends', NOW)
    assert result['status'] == 'complete'
    data = concerts.list_concerts('friends', NOW)
    assert data['events'][0]['event_id'] == 'event-1'
    assert data['events'][0]['interested_users'] == ['jana']
    assert data['country'] == 'ES'
    assert data['stale'] is False
    assert concerts.list_concerts('other', NOW)['events'] == []


def test_tribute_attraction_does_not_match_actual_artist(discovery, monkeypatch):
    monkeypatch.setattr(concerts.ticketmaster, 'artist_events', lambda *args: [event(artist='Tributo a Malmö 040')])
    concerts.collect('friends', NOW)
    assert concerts.list_concerts('friends', NOW)['events'] == []


def test_failed_provider_scan_preserves_previous_result(discovery, monkeypatch):
    concerts.collect('friends', NOW)
    def fail(*args): raise RuntimeError('Provider unavailable')
    monkeypatch.setattr(concerts.ticketmaster, 'artist_events', fail)
    with pytest.raises(RuntimeError):
        concerts.collect('friends', NOW + timedelta(hours=1))
    result = concerts.list_concerts('friends', NOW + timedelta(hours=1))
    assert len(result['events']) == 1
    assert result['last_scan_at'] == NOW.isoformat()


def test_failure_while_writing_does_not_hide_previous_snapshot(discovery, monkeypatch):
    concerts.collect('friends', NOW)
    real_resource = concerts.boto3.resource
    original = real_resource('dynamodb').Table('sfw-test')
    class BrokenTable:
        def update_item(self, **kwargs): raise RuntimeError('Storage unavailable')
    class Resource:
        def Table(self, name): return BrokenTable()
    monkeypatch.setattr(concerts.boto3, 'resource', lambda name: Resource())
    with pytest.raises(RuntimeError):
        concerts.collect('friends', NOW + timedelta(hours=1))
    monkeypatch.setattr(concerts.boto3, 'resource', real_resource)
    assert len(concerts.list_concerts('friends', NOW)['events']) == 1


def test_latest_empty_result_hides_old_events_and_old_scans_cannot_replace_new(discovery, monkeypatch):
    concerts.collect('friends', NOW)
    monkeypatch.setattr(concerts.ticketmaster, 'artist_events', lambda *args: [])
    concerts.collect('friends', NOW + timedelta(hours=1))
    assert concerts.list_concerts('friends', NOW + timedelta(hours=1))['events'] == []
    assert concerts.collect('friends', NOW)['status'] == 'superseded'


def test_disabled_feature_does_not_query_cache(setup, monkeypatch):
    allow(); userinfo(monkeypatch); dashboard.store.add_member('friends', 'anna', 'Anna')
    monkeypatch.setenv('CONCERTS_ENABLED', 'false')
    result = dashboard.handler(request('/api/concerts'), None)
    assert result['statusCode'] == 200
    assert json.loads(result['body'])['enabled'] is False


def test_concert_api_uses_authenticated_group_not_requested_group(setup, monkeypatch):
    allow(); userinfo(monkeypatch); dashboard.store.add_member('friends', 'anna', 'Anna')
    monkeypatch.setenv('CONCERTS_ENABLED', 'true')
    called = []
    monkeypatch.setattr(dashboard.concerts, 'list_concerts', lambda group, now: called.append(group) or {'events': []})
    event_request = request('/api/concerts'); event_request['queryStringParameters'] = {'group_id': 'other'}
    assert dashboard.handler(event_request, None)['statusCode'] == 200
    assert called == ['friends']
    assert dashboard.handler({'rawPath': '/api/concerts'}, None)['statusCode'] == 403
