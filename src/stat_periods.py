"""Calendar ranges shared by hosted and local statistics (Europe/Madrid)."""
from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo

MADRID = ZoneInfo('Europe/Madrid')


def utc_iso(moment):
    return moment.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def bounds(period, now, month=None):
    now = now.astimezone(MADRID)
    if period not in ('all', 'today', '7d', 'month'):
        raise ValueError('Periodo inválido.')
    if period == 'all':
        return '0000', utc_iso(now)
    if period == 'month':
        if not month or not re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', month):
            raise ValueError('Elige un mes válido con formato AAAA-MM.')
        if month > now.strftime('%Y-%m'):
            raise ValueError('El mes no puede ser posterior al actual.')
        year, number = map(int, month.split('-'))
        if year < 1:
            raise ValueError('Elige un año válido.')
        start = datetime(year, number, 1, tzinfo=MADRID)
        end = datetime(year + (number == 12), number % 12 + 1, 1, tzinfo=MADRID)
        return utc_iso(start), utc_iso(min(end, now))
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == '7d':
        start -= timedelta(days=6)
    return utc_iso(start), utc_iso(now)
