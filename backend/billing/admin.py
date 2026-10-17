from django.contrib import admin
from django.db.models import Count, QuerySet

from .models import BillingRun, Invoice, InvoiceLineItem


class InvoiceLineItemInline(admin.TabularInline):
    model = InvoiceLineItem
    extra = 0
    readonly_fields = ['timesheet_entry', 'date', 'hours', 'rate', 'amount']


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['id', 'company', 'freelancer', 'month', 'total_amount', 'email_status', 'created_at']
    list_filter = ['email_status', 'month', 'company']
    list_select_related = ['company', 'freelancer']
    inlines = [InvoiceLineItemInline]
    raw_id_fields = ['company', 'freelancer']
    readonly_fields = ['billing_run']


@admin.register(BillingRun)
class BillingRunAdmin(admin.ModelAdmin):
    list_display = ['id', 'company', 'month', 'created_by', 'invoice_count', 'created_at']
    list_filter = ['company', 'month']
    list_select_related = ['company', 'created_by']
    raw_id_fields = ['company', 'created_by']

    @admin.display(description='Invoices generated')
    def invoice_count(self, obj) -> int:
        return obj.invoice_count

    def get_queryset(self, request) -> QuerySet[BillingRun]:
        return super().get_queryset(request=request).annotate(
            invoice_count=Count('invoices')
        )
