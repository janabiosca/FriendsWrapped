"""Discovery queries must avoid false artist matches, key leaks and unsafe links."""
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import urllib.error

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import ticketmaster

NOW = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)


def event(event_id='event-1', artist='Malmö 040', country='ES'):
    return {'id': event_id, 'name': artist + ' en directo', 'url': 'https://www.ticketmaster.es/event/test',
            'dates': {'status': {'code': 'onsale'}, 'timezone': 'Europe/Madrid',
                      'start': {'localDate': '2026-12-20', 'localTime': '20:00:00', 'dateTime': '2026-12-20T19:00:00Z'}},
            '_embedded': {'attractions': [{'name': artist}], 'venues': [
                {'name': 'Sala', 'country': {'countryCode': country}, 'city': {'name': 'Madrid'}}]}}


def test_exact_normalized_artist_match_and_spain_filter(monkeypatch):
    calls = []
    def pages(path, key, params):
        calls.append((path, params))
        if path == 'attractions':
            return [{'id': 'real', 'name': 'Malmo 040'}, {'id': 'tribute', 'name': 'Tributo a Malmö 040'}]
        return []
    monkeypatch.setattr(ticketmaster, 'pages', pages)
    ticketmaster.artist_events('secret', 'Malmö 040', NOW)
    assert calls[1][1]['attractionId'] == 'real'
    assert calls[1][1]['countryCode'] == 'ES'


def test_pagination_limit_fails_instead_of_claiming_complete_results(monkeypatch):
    monkeypatch.setattr(ticketmaster, 'get', lambda *args: {'page': {'totalPages': 6}})
    with pytest.raises(ticketmaster.TicketmasterError, match='pagination limit'):
        ticketmaster.pages('events', 'secret', {})


def test_http_exception_never_exposes_the_key(monkeypatch):
    def fail(*args, **kwargs):
        raise urllib.error.HTTPError('https://app.ticketmaster.com/?apikey=TOPSECRET', 401, 'Unauthorized', {}, None)
    monkeypatch.setattr(ticketmaster.urllib.request, 'urlopen', fail)
    with pytest.raises(ticketmaster.TicketmasterError) as error:
        ticketmaster.get('events', 'TOPSECRET', {})
    assert 'TOPSECRET' not in str(error.value)
    assert '401' in str(error.value)


@pytest.mark.parametrize('change', ['cancelled', 'postponed', 'outside-spain', 'past'])
def test_unavailable_or_out_of_scope_events_are_excluded(change):
    item = event()
    if change in ('cancelled', 'postponed'):
        item['dates']['status']['code'] = change
    elif change == 'outside-spain':
        item['_embedded']['venues'][0]['country']['countryCode'] = 'FR'
    else:
        item['dates']['start']['dateTime'] = '2026-10-20T19:00:00Z'
        item['dates']['start']['localDate'] = '2026-10-20'
    assert ticketmaster.event_details(item, NOW) is None


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'https://ticketmaster.es.evil.example/event', 'https://user:password@ticketmaster.es/event'])
def test_untrusted_links_are_removed(url):
    item = event(); item['url'] = url
    assert ticketmaster.event_details(item, NOW)['url'] == ''
