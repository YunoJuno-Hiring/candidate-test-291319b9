import datetime
import logging
from decimal import Decimal

from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from accounts.models import Company
from contracts.models import TimesheetEntry

from .models import BillingRun, Invoice, InvoiceLineItem

logger = logging.getLogger(__name__)


def bill_freelancer(
    company: Company, freelancer_id: int, month: datetime.date, billing_run: BillingRun
) -> Invoice | None:
    """
    Create one invoice for a single freelancer's entries.

    Locks each candidate entry with SELECT ... FOR UPDATE SKIP LOCKED inside
    its own transaction: a concurrent billing run can't see rows this
    transaction already has locked, so it naturally picks only what's left
    unclaimed rather than racing for the same entries.
    """
    with transaction.atomic():
        entries = list(
            TimesheetEntry.objects.approved().unbilled().in_month(month).for_company(company)
            .filter(contract__freelancer_id=freelancer_id)
            .select_related('contract')
            .select_for_update(skip_locked=True, of=('self',))
            .order_by('date')
        )
        if not entries:
            logger.debug(
                'No lockable entries for freelancer %s in %s.',
                freelancer_id, month,
            )
            return None

        invoice = Invoice.objects.create(
            company=company,
            freelancer_id=freelancer_id,
            month=month,
            total_amount=Decimal('0.00'),
            billing_run=billing_run,
        )
        line_items = [
            InvoiceLineItem(
                invoice=invoice,
                timesheet_entry=entry,
                date=entry.date,
                hours=entry.hours,
                rate=entry.contract.daily_rate,
                amount=entry.amount,
            )
            for entry in entries
        ]
        InvoiceLineItem.objects.bulk_create(line_items)

        invoice.total_amount = sum((li.amount for li in line_items), Decimal('0.00'))
        invoice.save(update_fields=['total_amount'])

    logger.debug('Created invoice %s for freelancer %s at company %s', invoice.pk, freelancer_id, company.pk)
    transaction.on_commit(lambda: send_invoice_email(invoice))
    return invoice


def render_invoice_body(invoice: Invoice) -> str:
    return '\n'.join([
        f'Invoice for {invoice.freelancer.name} at {invoice.company.name}',
        f'Period: {invoice.month:%B %Y}',
        '',
        *[
            f'{li.date} — {li.hours}h @ £{li.rate}/day = £{li.amount}'
            for li in invoice.line_items.all()
        ],
        '',
        f'Total: £{invoice.total_amount}'
    ])


def send_invoice_email(invoice: Invoice) -> None:
    """
    Best-effort delivery of an already-committed invoice.

    Failure here never affects the invoice's existence — it's the record of
    what was billed, independent of whether the email made it out. Safe to
    call repeatedly, doesn't recompute invoices.
    """
    recipients = [invoice.company.billing_email, invoice.freelancer.user.email]
    try:
        send_mail(
            subject=f'Invoice for {invoice.freelancer.name} — {invoice.month:%B %Y}',
            message=render_invoice_body(invoice),
            from_email=None,
            recipient_list=recipients,
        )
    except Exception:
        logger.exception('Failed to send invoice email for invoice %s', invoice.pk)
        invoice.email_status = Invoice.EMAIL_FAILED
    else:
        logger.info('Sent email for invoice %s', invoice.pk)
        invoice.email_status = Invoice.EMAIL_SENT
        invoice.email_sent_at = timezone.now()
    finally:
        invoice.email_attempts += 1
        invoice.save(update_fields=['email_status', 'email_sent_at', 'email_attempts'])
