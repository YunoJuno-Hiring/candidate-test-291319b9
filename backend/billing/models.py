from django.conf import settings
from django.db import models

from accounts.models import Company, Freelancer
from contracts.models import TimesheetEntry


class BillingRun(models.Model):
    """Audit record of a single billing-run request.

    Written once per POST to /api/billing/runs/, even when it produces zero
    invoices — gives a real audit log of who ran billing, when, and for
    which period.
    """

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='billing_runs')
    month = models.DateField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class Invoice(models.Model):
    """
    An invoice for a company and freelancer for a month/year
    """
    EMAIL_PENDING = 'pending'
    EMAIL_SENT = 'sent'
    EMAIL_FAILED = 'failed'
    EMAIL_STATUS_CHOICES = [
        (EMAIL_PENDING, 'Pending'),
        (EMAIL_SENT, 'Sent'),
        (EMAIL_FAILED, 'Failed'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='invoices')
    freelancer = models.ForeignKey(Freelancer, on_delete=models.PROTECT, related_name='invoices')
    month = models.DateField(help_text='Normalised to the last day of the billed month.')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    email_status = models.CharField(
        max_length=10, choices=EMAIL_STATUS_CHOICES, default=EMAIL_PENDING
    )
    email_sent_at = models.DateTimeField(null=True, blank=True)
    email_attempts = models.PositiveIntegerField(default=0)

    billing_run = models.ForeignKey(
        BillingRun, on_delete=models.PROTECT, related_name='invoices'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Invoice {self.number} — {self.freelancer.name} @ {self.company.name} ({self.month:%Y-%m})'

    @property
    def number(self) -> str:
        return f'#{self.pk}'


class InvoiceLineItem(models.Model):
    """
    One billed timesheet entry line for an invoice.
    """

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='line_items')
    timesheet_entry = models.OneToOneField(
        TimesheetEntry, on_delete=models.PROTECT, related_name='invoice_line_item'
    )
    date = models.DateField()
    hours = models.DecimalField(max_digits=5, decimal_places=2)
    rate = models.DecimalField(max_digits=8, decimal_places=2)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f'{self.invoice.number} — {self.date} ({self.hours}h, £{self.amount})'
