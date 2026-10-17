import datetime
import logging

from django.contrib.auth.models import User

from accounts.models import Company
from contracts.models import TimesheetEntry

from .helpers import bill_freelancer
from .models import BillingRun

logger = logging.getLogger(__name__)


def run_billing(*, company: Company, month: datetime.date, created_by: User) -> BillingRun:
    """
    Generate invoices for a company's approved, not-yet-billed timesheet
    entries in the given month.

    Idempotent: entries already attached to an invoice line item (from an
    earlier run) are excluded, so re-running a month only bills whatever was
    approved since the last run. Issued invoices are never mutated — a later
    run for the same month produces a second, separate invoice.
    """
    billing_run = BillingRun.objects.create(company=company, month=month, created_by=created_by)
    logger.info(
        'Billing run %s started for %s (%s), triggered by %s',
        billing_run.pk, company.pk, month, created_by.pk,
    )

    freelancer_ids = (
        TimesheetEntry.objects.approved().unbilled().in_month(month).for_company(company)
        .values_list('contract__freelancer_id', flat=True)
        .distinct()
    )

    for freelancer_id in freelancer_ids:
        try:
            bill_freelancer(company, freelancer_id, month, billing_run)
        except Exception as exc:
            # One freelancer's failure shouldn't block billing the rest of the
            # company. Entries stay unbilled, so a later re-run picks them up
            # once whatever broke is fixed.
            logger.exception(
                'Failed to bill freelancer %s for %s (%s) in billing run %s',
                freelancer_id, company.pk, month, billing_run.pk,
                exc_info=exc,
            )

    logger.info(
        'Billing run %s completed: %s invoice(s) generated',
        billing_run.pk, billing_run.invoices.count(),
    )
    return billing_run
