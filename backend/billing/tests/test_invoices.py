import datetime
from decimal import Decimal
from unittest.mock import Mock

import pytest

from billing.models import BillingRun, Invoice, InvoiceLineItem


@pytest.mark.django_db
def test_invoice_list_scoped_to_own_company(admin_client, other_companys_invoice):
    resp = admin_client.get('/api/invoices/')
    assert resp.status_code == 200
    assert resp.data == []


@pytest.mark.django_db
def test_invoice_list_filters_by_month(admin_client, northstar, admin_user, active_contract, month):
    run = BillingRun.objects.create(company=northstar, month=month, created_by=admin_user)
    Invoice.objects.create(
        company=northstar, freelancer=active_contract.freelancer, month=month,
        total_amount=Decimal('100.00'), billing_run=run,
    )
    other_month = datetime.date(2026, 5, 31)
    other_run = BillingRun.objects.create(company=northstar, month=other_month, created_by=admin_user)
    Invoice.objects.create(
        company=northstar, freelancer=active_contract.freelancer, month=other_month,
        total_amount=Decimal('50.00'), billing_run=other_run,
    )

    resp = admin_client.get('/api/invoices/?month=2026-04')
    assert resp.status_code == 200
    assert len(resp.data) == 1
    assert resp.data[0]['month'] == '2026-04-30'
    assert 'line_items' not in resp.data[0]


@pytest.mark.django_db
def test_invoice_list_requires_company_admin(freelancer_client):
    resp = freelancer_client.get('/api/invoices/')
    assert resp.status_code == 403


@pytest.mark.django_db
def test_invoice_detail_returns_line_items(admin_client, approved_entry, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        admin_client.post('/api/billing/runs/', {'month': '2026-04'})
    invoice = Invoice.objects.get()

    resp = admin_client.get(f'/api/invoices/{invoice.id}/')
    assert resp.status_code == 200
    assert len(resp.data['line_items']) == 1
    assert resp.data['total_amount'] == str(invoice.total_amount)


@pytest.mark.django_db
def test_invoice_detail_404_for_other_companys_invoice(admin_client, other_companys_invoice):
    resp = admin_client.get(f'/api/invoices/{other_companys_invoice.id}/')
    assert resp.status_code == 404


@pytest.mark.django_db
def test_resend_flips_status_and_increments_attempts(
    admin_client, approved_entry, django_capture_on_commit_callbacks, monkeypatch
):
    monkeypatch.setattr('billing.helpers.send_mail', Mock(side_effect=Exception('smtp down')))
    with django_capture_on_commit_callbacks(execute=True):
        admin_client.post('/api/billing/runs/', {'month': '2026-04'})
    invoice = Invoice.objects.get()
    assert invoice.email_status == Invoice.EMAIL_FAILED
    assert invoice.email_attempts == 1

    monkeypatch.undo()  # let the next send succeed
    line_items_before = list(InvoiceLineItem.objects.values_list('id', 'amount'))

    resp = admin_client.post(f'/api/invoices/{invoice.id}/resend/')
    assert resp.status_code == 200
    assert resp.data['email_status'] == Invoice.EMAIL_SENT

    invoice.refresh_from_db()
    assert invoice.email_attempts == 2
    assert list(InvoiceLineItem.objects.values_list('id', 'amount')) == line_items_before


@pytest.mark.django_db
def test_resend_404_for_other_companys_invoice(admin_client, other_companys_invoice):
    resp = admin_client.post(f'/api/invoices/{other_companys_invoice.id}/resend/')
    assert resp.status_code == 404
