"""Availability notices preserve reports and suppress completed or concurrent sends."""
from datetime import date
from pathlib import Path
import sys

import boto3
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import wrapped
import wrapped_notifications as notices
from test_spotify_connect import setup
from test_wrapped import report_store, prepare


@pytest.fixture
def ready_notice(report_store, monkeypatch):
    monkeypatch.setenv('DASHBOARD_URL', 'https://dashboard.example.com/')
    monkeypatch.setenv('NOTICE_TOPIC_ARN', 'arn:aws:sns:us-east-1:123456789012:existing-alarms')
    monkeypatch.setattr(wrapped, 'previous_week', lambda reference=None: date(2026, 11, 9))
    return wrapped.archive(prepare())


def table():
    return boto3.resource('dynamodb').Table('sfw-test')


def key():
    return {'PK': 'GROUP#friends', 'SK': 'WRAPPED_NOTICE#2026-11-09'}


def publisher(monkeypatch):
    class SNS:
        calls = []
        def publish(self, **kwargs):
            self.calls.append(kwargs)
            return {'MessageId': 'message-1'}
    client = SNS()
    monkeypatch.setattr(notices, 'sns_client', lambda: client)
    return client


def test_retry_does_not_publish_again_and_notice_has_no_listening_details(ready_notice, monkeypatch):
    sns = publisher(monkeypatch)
    original = wrapped.read_object(ready_notice['pdf_key'])
    assert notices.notify(ready_notice)['notification_status'] == 'published'
    assert notices.notify(ready_notice)['notification_status'] == 'already_published'
    assert len(sns.calls) == 1
    message = sns.calls[0]
    assert message['TopicArn'].endswith(':existing-alarms')
    assert 'https://dashboard.example.com/' in message['Message']
    assert 'Inicia sesión' in message['Message']
    assert 'Artist' not in message['Message']
    assert wrapped.read_object(ready_notice['pdf_key']) == original
    receipt = table().get_item(Key=key())['Item']
    assert receipt['notice_status'] == 'sent'
    assert 'lease_until' not in receipt


def test_live_lease_rejects_concurrent_publisher(ready_notice, monkeypatch):
    sns = publisher(monkeypatch)
    monkeypatch.setattr(notices.time, 'time', lambda: 1000)
    table().put_item(Item={**key(), 'notice_status': 'sending', 'owner': 'other', 'lease_until': 1100})
    with pytest.raises(notices.NotificationBusy):
        notices.notify(ready_notice)
    assert sns.calls == []


def test_expired_lease_can_be_recovered(ready_notice, monkeypatch):
    sns = publisher(monkeypatch)
    monkeypatch.setattr(notices.time, 'time', lambda: 1000)
    table().put_item(Item={**key(), 'notice_status': 'sending', 'owner': 'crashed', 'lease_until': 999})
    assert notices.notify(ready_notice)['notification_status'] == 'published'
    assert len(sns.calls) == 1


def test_publish_failure_remains_retryable(ready_notice, monkeypatch):
    client = publisher(monkeypatch)
    real_publish = client.publish
    def fail(**kwargs):
        raise RuntimeError('SNS unavailable')
    monkeypatch.setattr(client, 'publish', fail)
    with pytest.raises(RuntimeError, match='SNS unavailable'):
        notices.notify(ready_notice, owner='first-attempt')
    receipt = table().get_item(Key=key())['Item']
    assert receipt['notice_status'] == 'pending'
    monkeypatch.setattr(client, 'publish', real_publish)
    assert notices.notify(ready_notice, owner='retry')['notification_status'] == 'published'


def test_crash_after_publish_does_not_immediately_republish(ready_notice, monkeypatch):
    sns = publisher(monkeypatch)
    monkeypatch.setattr(notices.time, 'time', lambda: 1000)
    real_resource = notices.boto3.resource
    real_table = real_resource('dynamodb').Table('sfw-test')
    class BrokenReceiptTable:
        def put_item(self, **kwargs): return real_table.put_item(**kwargs)
        def get_item(self, **kwargs): return real_table.get_item(**kwargs)
        def update_item(self, **kwargs): raise RuntimeError('Receipt write failed')
    class Resource:
        def Table(self, name): return BrokenReceiptTable()
    monkeypatch.setattr(notices.boto3, 'resource', lambda name: Resource())
    with pytest.raises(RuntimeError, match='Receipt write failed'):
        notices.notify(ready_notice)
    with pytest.raises(notices.NotificationBusy):
        notices.notify(ready_notice)
    assert len(sns.calls) == 1


def test_missing_pdf_never_sends_notice(ready_notice, monkeypatch):
    sns = publisher(monkeypatch)
    boto3.client('s3').delete_object(Bucket='sfw-wrapped-test', Key=ready_notice['pdf_key'])
    with pytest.raises(ValueError, match='PDF is not available'):
        notices.notify(ready_notice)
    assert sns.calls == []
    assert 'Item' not in table().get_item(Key=key())


def test_historical_week_does_not_link_to_a_different_report(ready_notice, monkeypatch):
    sns = publisher(monkeypatch)
    monkeypatch.setattr(wrapped, 'previous_week', lambda reference=None: date(2026, 11, 16))
    assert notices.notify(ready_notice)['notification_status'] == 'historical_week_skipped'
    assert sns.calls == []


def test_other_groups_report_is_rejected(ready_notice, monkeypatch):
    sns = publisher(monkeypatch)
    with pytest.raises(ValueError):
        notices.notify({**ready_notice, 'group_id': 'other'})
    assert sns.calls == []


def test_handler_routes_notice_action(ready_notice, monkeypatch):
    sns = publisher(monkeypatch)
    result = wrapped.handler({'action': 'notify', 'snapshot': ready_notice}, None)
    assert result['notification_status'] == 'published'
    assert len(sns.calls) == 1
