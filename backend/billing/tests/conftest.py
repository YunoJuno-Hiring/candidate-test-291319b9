import datetime
from decimal import Decimal

import pytest

from billing.models import BillingRun, Invoice

MONTH = datetime.date(2026, 4, 30)  # last day of April — matches what MonthField produces


@pytest.fixture
def month():
    return MONTH


@pytest.fixture
def other_companys_invoice(meridian, admin_user, other_contract, month):
    """An invoice belonging to meridian — northstar admins must never see or touch it."""
    billing_run = BillingRun.objects.create(company=meridian, month=month, created_by=admin_user)
    return Invoice.objects.create(
        company=meridian,
        freelancer=other_contract.freelancer,
        month=month,
        total_amount=Decimal('100.00'),
        billing_run=billing_run,
    )