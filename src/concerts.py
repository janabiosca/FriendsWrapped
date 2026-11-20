"""Daily concert discovery for the group's top artists; results are shared in the app."""
from datetime import datetime, timedelta, timezone
import json
import os
import uuid

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from zoneinfo import ZoneInfo

import listening_stats
import store
import ticketmaster


def preferences(group_id, now):
    start = (now - timedelta(days=30)).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    end = now.isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    artists = {}
    for user_id in store.group_members(group_id):
        top = listening_stats.summarize(store.plays_between(user_id, start, end))['top_artists']
        for item in top:
            key = ticketmaster.normalize(item['name'])
            artists.setdefault(key, {'name': item['name'], 'user_ids': set()})['user_ids'].add(user_id)
    return artists


def collect(group_id, now):
    secret = boto3.client('secretsmanager').get_secret_value(SecretId=os.environ['TICKETMASTER_SECRET'])
    api_key = json.loads(secret['SecretString'])['api_key']
    matches = {}
    for normalized, artist in preferences(group_id, now).items():
        for event in ticketmaster.artist_events(api_key, artist['name'], now):
            details = ticketmaster.event_details(event, now)
            if details is None:
                continue
            # Verify the event embeds the attraction, avoiding keyword matches to tribute acts.
            event_artists = event.get('_embedded', {}).get('attractions', [])
            if not any(ticketmaster.normalize(item.get('name', '')) == normalized for item in event_artists):
                continue
            found = matches.setdefault(details['event_id'], {'details': details, 'artists': set(), 'users': set()})
            found['artists'].add(artist['name'])
            found['users'].update(artist['user_ids'])
    table = boto3.resource('dynamodb').Table(os.environ['TABLE_NAME'])
    synced_at = now.astimezone(timezone.utc).isoformat()
    scan_id = uuid.uuid4().hex
    # Finish all remote queries before persisting. A failed query preserves the prior successful scan.
    for match in matches.values():
        details = match['details']
        table.update_item(
            Key={'PK': 'GROUP#' + group_id, 'SK': 'CONCERT#' + scan_id + '#' + details['event_id']},
            UpdateExpression='SET details = :d, artists = :a, interested_users = :u, '
                             'last_seen_at = :t, first_seen_at = if_not_exists(first_seen_at, :t)',
            ExpressionAttributeValues={':d': details, ':a': sorted(match['artists']),
                                       ':u': sorted(match['users']), ':t': synced_at},
        )
    try:
        table.put_item(
            Item={'PK': 'GROUP#' + group_id, 'SK': 'CONCERT_SCAN', 'scan_id': scan_id,
                  'last_scan_at': synced_at, 'events_found': len(matches), 'country': 'ES'},
            ConditionExpression='attribute_not_exists(last_scan_at) OR last_scan_at <= :now',
            ExpressionAttributeValues={':now': synced_at})
    except ClientError as error:
        if error.response['Error']['Code'] != 'ConditionalCheckFailedException':
            raise
        return {'events_found': len(matches), 'last_scan_at': synced_at, 'status': 'superseded'}
    return {'events_found': len(matches), 'last_scan_at': synced_at, 'status': 'complete'}



def list_concerts(group_id, now):
    table = boto3.resource('dynamodb').Table(os.environ['TABLE_NAME'])
    scan = table.get_item(Key={'PK': 'GROUP#' + group_id, 'SK': 'CONCERT_SCAN'},
                          ConsistentRead=True).get('Item')
    if not scan:
        return {'events': [], 'last_scan_at': None, 'country': 'ES', 'stale': False}
    events, pagination = [], {}
    while True:
        page = table.query(KeyConditionExpression=Key('PK').eq('GROUP#' + group_id)
                           & Key('SK').begins_with('CONCERT#' + scan['scan_id'] + '#'), ConsistentRead=True, **pagination)
        for item in page['Items']:
            if item['last_seen_at'] != scan['last_scan_at']:
                continue
            details = item['details']
            if details['date_time']:
                future = datetime.fromisoformat(details['date_time'].replace('Z', '+00:00')) >= now
            else:
                future = details['local_date'] >= now.astimezone(ZoneInfo(details['timezone'])).date().isoformat()
            if future:
                events.append({**details, 'artists': item['artists'], 'interested_users': item['interested_users']})
        if not page.get('LastEvaluatedKey'):
            break
        pagination['ExclusiveStartKey'] = page['LastEvaluatedKey']
    events.sort(key=lambda event: (event['local_date'], event.get('local_time') or '', event['event_id']))
    return {'events': events, 'last_scan_at': scan['last_scan_at'], 'country': 'ES',
            'stale': now - datetime.fromisoformat(scan['last_scan_at']) > timedelta(hours=48)}


def handler(event, context):
    try:
        result = collect(os.environ['GROUP_ID'], datetime.now(timezone.utc))
    except Exception:
        print(json.dumps({'event': 'concert_scan_failed'}))
        raise ticketmaster.TicketmasterError('Concert discovery failed; verify credentials and provider availability') from None
    print(json.dumps({'event': 'concert_scan_completed', **result}))
    return result
