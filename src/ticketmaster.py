"""Ticketmaster Discovery client with bounded pagination and exact artist matching."""
from datetime import date, datetime, timezone
import json
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

BASE_URL = 'https://app.ticketmaster.com/discovery/v2/'
PAGE_SIZE = 200
_last_request = 0.0
MAX_PAGES = 5  # Discovery deep pagination permits at most 1,000 records.


class TicketmasterError(Exception):
    pass


def normalize(name):
    value = unicodedata.normalize('NFKD', name.casefold())
    return ''.join(char for char in value if char.isalnum() and not unicodedata.combining(char))


def get(path, api_key, params):
    global _last_request
    if path not in ('attractions', 'events'):
        raise ValueError('Unsupported Discovery resource')
    time.sleep(max(0, 0.25 - (time.monotonic() - _last_request)))
    _last_request = time.monotonic()
    query = urllib.parse.urlencode({**params, 'apikey': api_key})
    try:
        with urllib.request.urlopen(BASE_URL + path + '.json?' + query, timeout=10) as result:
            data = json.load(result)
            if not isinstance(data, dict):
                raise ValueError("Unexpected Discovery response")
            return data
    except urllib.error.HTTPError as error:
        # urllib errors may contain the URL and API key. Never expose their body or URL.
        raise TicketmasterError(f'Ticketmaster HTTP {error.code}') from None
    except (OSError, ValueError):
        raise TicketmasterError('Ticketmaster connection failed') from None


def pages(path, api_key, params):
    items = []
    for page in range(MAX_PAGES):
        response = get(path, api_key, {**params, 'size': PAGE_SIZE, 'page': page})
        items.extend(response.get('_embedded', {}).get(path, []))
        total = int(response.get('page', {}).get('totalPages', 1))
        if total > MAX_PAGES:
            raise TicketmasterError('Ticketmaster pagination limit reached')
        if page + 1 >= total:
            return items
    return items


def artist_events(api_key, artist, now):
    attractions = pages('attractions', api_key, {'keyword': artist})
    ids = sorted({item['id'] for item in attractions
                  if item.get('id') and normalize(item.get('name', '')) == normalize(artist)})
    if not ids:
        return []
    params = {'attractionId': ','.join(ids), 'countryCode': 'ES', 'classificationName': 'music',
              'startDateTime': now.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
              'sort': 'date,asc'}
    return pages('events', api_key, params)


def event_details(event, now):
    dates = event.get('dates', {})
    status = dates.get('status', {}).get('code', 'unknown')
    start = dates.get('start', {})
    day = start.get('localDate')
    if status in ('cancelled', 'canceled', 'postponed') or not day or start.get('dateTBA') or start.get('dateTBD'):
        return None
    date.fromisoformat(day)
    instant = start.get('dateTime')
    if instant:
        moment = datetime.fromisoformat(instant.replace('Z', '+00:00'))
        if moment.tzinfo is None or moment < now:
            return None
    venues = event.get('_embedded', {}).get('venues', [])
    venue = venues[0] if venues else {}
    if venue.get('country', {}).get('countryCode') != 'ES':
        return None
    zone = dates.get('timezone') or venue.get('timezone', 'Europe/Madrid')
    if date.fromisoformat(day) < now.astimezone(ZoneInfo(zone)).date():
        return None
    url = event.get('url', '')
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or ''
    trusted = any(host == domain or host.endswith('.' + domain) for domain in ('ticketmaster.es', 'ticketmaster.com'))
    if parsed.scheme != 'https' or not trusted or parsed.username or parsed.password:
        url = ''
    return {'event_id': event['id'], 'name': event.get('name', 'Concierto'),
            'date_time': instant, 'local_date': day, 'local_time': start.get('localTime'),
            'timezone': zone,
            'venue': venue.get('name', ''), 'city': venue.get('city', {}).get('name', ''),
            'status': status, 'url': url}
