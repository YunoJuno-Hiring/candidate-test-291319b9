import pytest
import datetime
from billing.serializers import MonthField


@pytest.mark.parametrize(
    ["value", "expected"],
    [
        ["2026-01", datetime.date(2026, 1, 31)],
        ["2026-04", datetime.date(2026, 4, 30)],
        ["2026-02", datetime.date(2026, 2, 28)],
        ["2024-02", datetime.date(2024, 2, 29)],
        ["1900-02", datetime.date(1900, 2, 28)],
        ["2000-02", datetime.date(2000, 2, 29)],
    ],
    ids=[
        "31-day-month",
        "30-day-month",
        "feb-non-leap",
        "feb-leap",
        "century-non-leap",
        "century-leap",
    ],
)
def test_month_field_returns_last_day_of_month(value, expected):
    assert MonthField().to_internal_value(value) == expected
