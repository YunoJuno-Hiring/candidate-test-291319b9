import datetime

from decimal import Decimal, ROUND_HALF_UP

from django.db import models

from accounts.models import Company, Freelancer


class Contract(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_CLOSED = 'closed'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_CLOSED, 'Closed'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='contracts')
    freelancer = models.ForeignKey(Freelancer, on_delete=models.CASCADE, related_name='contracts')
    daily_rate = models.DecimalField(max_digits=8, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE)

    def __str__(self):
        return f'{self.freelancer.name} @ {self.company.name} ({self.status})'


class TimesheetEntryQuerySet(models.QuerySet):
    def approved(self) -> models.QuerySet['TimesheetEntry']:
        return self.filter(status=TimesheetEntry.STATUS_APPROVED)

    def unbilled(self) -> models.QuerySet['TimesheetEntry']:
        """Entries with no invoice line item yet — i.e. not billed by any run."""
        return self.filter(invoice_line_item__isnull=True)

    def in_month(self, month: datetime.date) -> models.QuerySet['TimesheetEntry']:
        return self.filter(date__year=month.year, date__month=month.month)

    def for_company(self, company: Company) -> models.QuerySet['TimesheetEntry']:
        return self.filter(contract__company=company)


class TimesheetEntry(models.Model):
    HOURS_PER_DAY = 8

    STATUS_DRAFT = 'draft'
    STATUS_SUBMITTED = 'submitted'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_SUBMITTED, 'Submitted'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='timesheet_entries')
    date = models.DateField()
    hours = models.DecimalField(max_digits=5, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    rejection_reason = models.TextField(blank=True, null=True)

    objects = TimesheetEntryQuerySet.as_manager()

    class Meta:
        unique_together = ('contract', 'date')
        ordering = ['-date']

    def __str__(self):
        return f'{self.contract} — {self.date} ({self.hours}h, {self.status})'

    @property
    def amount(self) -> Decimal:
        """
        Billable value of this entry: hours worked as a fraction of a full day.
        """
        return (self.hours * self.contract.daily_rate / self.HOURS_PER_DAY).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
