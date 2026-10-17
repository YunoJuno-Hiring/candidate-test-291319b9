import logging

from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCompanyAdmin

from .models import Invoice
from .serializers import (
    BillingRunCreateSerializer,
    InvoiceFilterSerializer,
    InvoiceListSerializer,
    InvoiceSerializer,
)
from .helpers import send_invoice_email
from .tasks import run_billing

logger = logging.getLogger(__name__)


class BillingRunView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    def post(self, request):
        serializer = BillingRunCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        billing_run = run_billing(
            company=request.user.company_admin.company,
            month=serializer.validated_data['month'],
            created_by=request.user,
        )
        return Response({
            'run_id': str(billing_run.id),
            'invoices_generated': billing_run.invoices.count(),
            'status': 'completed',
        })


class InvoiceListView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    def get(self, request):
        filter_serializer = InvoiceFilterSerializer(data=request.query_params)
        filter_serializer.is_valid(raise_exception=True)

        qs = Invoice.objects.filter(
            company=request.user.company_admin.company
        ).select_related('company', 'freelancer')

        month = filter_serializer.validated_data.get('month')
        if month is not None:
            qs = qs.filter(month=month)

        return Response(InvoiceListSerializer(qs, many=True).data)


class InvoiceDetailView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    def get(self, request, pk):
        invoice = get_object_or_404(
            Invoice.objects.select_related('company', 'freelancer').prefetch_related('line_items'),
            pk=pk, company=request.user.company_admin.company,
        )
        return Response(InvoiceSerializer(invoice).data)


class InvoiceResendView(APIView):
    permission_classes = [IsAuthenticated, IsCompanyAdmin]

    def post(self, request, pk):
        invoice = get_object_or_404(
            Invoice.objects.select_related('company', 'freelancer__user'),
            pk=pk, company=request.user.company_admin.company,
        )

        logger.info('Invoice %s resend triggered by user %s', invoice.pk, request.user.pk)

        # Line items/total are already frozen — this only re-attempts delivery,
        # it never recomputes what was billed. Safe to call repeatedly.
        send_invoice_email(invoice)
        return Response(InvoiceSerializer(invoice).data)
