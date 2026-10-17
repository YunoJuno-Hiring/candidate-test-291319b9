import calendar

from rest_framework import serializers

from accounts.serializers import CompanySerializer, FreelancerSerializer

from .models import Invoice, InvoiceLineItem


class MonthField(serializers.DateField):
    """A 'YYYY-MM' value, parsed to the last day of that month (a billing period's end)."""

    def __init__(self, **kwargs):
        kwargs.setdefault('input_formats', ['%Y-%m'])
        kwargs.setdefault('error_messages', {'invalid': 'Expected a YYYY-MM value.'})
        super().__init__(**kwargs)

    def to_internal_value(self, value):
        parsed = super().to_internal_value(value)
        last_day = calendar.monthrange(parsed.year, parsed.month)[1]
        return parsed.replace(day=last_day)


class BillingRunCreateSerializer(serializers.Serializer):
    month = MonthField()


class InvoiceFilterSerializer(serializers.Serializer):
    month = MonthField(required=False)


class InvoiceLineItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLineItem
        fields = ['id', 'date', 'hours', 'rate', 'amount']


class InvoiceSerializer(serializers.ModelSerializer):
    company = CompanySerializer(read_only=True)
    freelancer = FreelancerSerializer(read_only=True)
    line_items = InvoiceLineItemSerializer(many=True, read_only=True)
    number = serializers.CharField(read_only=True)

    class Meta:
        model = Invoice
        fields = [
            'id', 'number', 'company', 'freelancer', 'month', 'total_amount',
            'email_status', 'email_sent_at', 'email_attempts',
            'created_at', 'line_items',
        ]


class InvoiceListSerializer(serializers.ModelSerializer):
    """Lighter shape for invoice list — no line items."""

    company = CompanySerializer(read_only=True)
    freelancer = FreelancerSerializer(read_only=True)
    number = serializers.CharField(read_only=True)

    class Meta:
        model = Invoice
        fields = [
            'id', 'number', 'company', 'freelancer', 'month', 'total_amount',
            'email_status', 'created_at',
        ]
