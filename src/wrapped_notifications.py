"""SNS availability notices with a per-week durable receipt and an expiring send lease."""
from datetime import date, timedelta
import os
import time
from urllib.parse import urlsplit
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

import wrapped

LEASE_SECONDS = 180  # Longer than the Wrapped Lambda timeout; abandoned claims can be retried.


class NotificationBusy(RuntimeError):
    pass


MONTHS = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
          'septiembre', 'octubre', 'noviembre', 'diciembre')
SHORT_MONTHS = ('ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic')


def week_label(monday, end):
    """'lunes 9 al domingo 15 de noviembre' (the month is repeated only when it changes)."""
    first = f'{monday.day}' if monday.month == end.month else f'{monday.day} de {MONTHS[monday.month - 1]}'
    return f'lunes {first} al domingo {end.day} de {MONTHS[end.month - 1]}'


def notice_subject(monday, end):
    # SNS email subjects must be ASCII: no accents or emoji here.
    span = (f'{monday.day}-{end.day} {SHORT_MONTHS[end.month - 1]}' if monday.month == end.month else
            f'{monday.day} {SHORT_MONTHS[monday.month - 1]} - {end.day} {SHORT_MONTHS[end.month - 1]}')
    return f'Vuestro Friends Wrapped ya esta listo ({span})'


def notice_message(monday, end, url):
    """Plain text (SNS email does not render HTML). No listening details: those stay behind login."""
    return (f'¡Hola! 👋\n\n'
            f'Ya está listo el Friends Wrapped del grupo 🎧\n'
            f'📅 Semana del {week_label(monday, end)}\n\n'
            f'¿Quién ha escuchado más? ¿Qué canción se os ha quedado pegada? 👀\n'
            f'Lo tenéis todo en el resumen de la semana.\n\n'
            f'👉 Entra aquí: {url}\n\n'
            f'Inicia sesión con tu cuenta del grupo y pulsa «Descargar Wrapped en PDF».\n\n'
            f'¡Nos escuchamos el lunes que viene! 💚\n'
            f'— Friends Wrapped')


def sns_client():
    return boto3.client('sns', config=Config(connect_timeout=5, read_timeout=10,
                        retries={'mode': 'standard', 'max_attempts': 2}))


def notify(manifest, owner=None):
    monday = date.fromisoformat(manifest['week_start'])
    expected = {**wrapped.keys(os.environ['GROUP_ID'], monday), 'status': 'ready'}
    if manifest != expected or monday.weekday() != 0:
        raise ValueError('Unexpected ready report location')
    if monday != wrapped.previous_week():
        # The dashboard downloads the latest complete week, not arbitrary historic reports.
        return {**manifest, 'notification_status': 'historical_week_skipped'}
    if wrapped.read_object(manifest['pdf_key']) is None:
        raise ValueError('The PDF is not available; no notice was sent')
    url = os.environ['DASHBOARD_URL']
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ('', '/')):
        raise ValueError('Configure the HTTPS dashboard home URL')
    topic = os.environ['NOTICE_TOPIC_ARN']
    owner = owner or uuid.uuid4().hex
    now = int(time.time())
    table = boto3.resource('dynamodb').Table(os.environ['TABLE_NAME'])
    key = {'PK': 'GROUP#' + manifest['group_id'], 'SK': 'WRAPPED_NOTICE#' + manifest['week_start']}
    try:
        table.put_item(
            Item={**key, 'notice_status': 'sending', 'owner': owner, 'lease_until': now + LEASE_SECONDS},
            ConditionExpression='attribute_not_exists(PK) OR (#state <> :sent AND lease_until <= :now)',
            ExpressionAttributeNames={'#state': 'notice_status'},
            ExpressionAttributeValues={':sent': 'sent', ':now': now})
    except ClientError as error:
        if error.response['Error']['Code'] != 'ConditionalCheckFailedException':
            raise
        receipt = table.get_item(Key=key, ConsistentRead=True).get('Item', {})
        if receipt.get('notice_status') == 'sent':
            return {**manifest, 'notification_status': 'already_published', 'message_id': receipt['message_id']}
        raise NotificationBusy('Another attempt is sending this weekly notice') from error
    end = monday + timedelta(days=6)
    try:
        result = sns_client().publish(
            TopicArn=topic,
            Subject=notice_subject(monday, end),
            Message=notice_message(monday, end, url))
    except Exception:
        # Leave a retryable record. A network timeout can still mean SNS accepted the
        # publish: standard SNS + DynamoDB cannot guarantee exactly-once email delivery.
        try:
            table.update_item(
                Key=key, UpdateExpression='SET notice_status = :pending, lease_until = :zero',
                ConditionExpression='#owner = :owner', ExpressionAttributeNames={'#owner': 'owner'},
                ExpressionAttributeValues={':pending': 'pending', ':zero': 0, ':owner': owner})
        except ClientError:
            pass  # Preserve the publish error; the lease also expires after a crash.
        raise
    table.update_item(
        Key=key,
        UpdateExpression='SET notice_status = :sent, message_id = :message, published_at = :now REMOVE lease_until, #owner',
        ConditionExpression='#owner = :owner', ExpressionAttributeNames={'#owner': 'owner'},
        ExpressionAttributeValues={':sent': 'sent', ':message': result['MessageId'], ':now': now, ':owner': owner})
    return {**manifest, 'notification_status': 'published', 'message_id': result['MessageId']}
