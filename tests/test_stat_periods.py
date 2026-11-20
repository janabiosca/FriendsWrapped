"""Calendar boundaries must follow Madrid DST and an exclusive next-month boundary."""
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import stat_periods

NOW = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize('month,start,end', [
    ('2026-03', '2026-02-28T23:00:00.000Z', '2026-03-31T22:00:00.000Z'),
    ('2026-10', '2026-09-30T22:00:00.000Z', '2026-10-31T23:00:00.000Z'),
    ('2024-02', '2024-01-31T23:00:00.000Z', '2024-02-29T23:00:00.000Z'),
    ('2025-12', '2025-11-30T23:00:00.000Z', '2025-12-31T23:00:00.000Z'),
    ('2026-11', '2026-10-31T23:00:00.000Z', '2026-11-20T12:00:00.000Z'),
])
def test_month_boundaries(month, start, end):
    assert stat_periods.bounds('month', NOW, month) == (start, end)


@pytest.mark.parametrize('month', [None, '', '2026-1', '2026-00', '2026-13', '0000-01', '2026-12', '2026-11-01'])
def test_missing_invalid_and_future_months_rejected(month):
    with pytest.raises(ValueError):
        stat_periods.bounds('month', NOW, month)
