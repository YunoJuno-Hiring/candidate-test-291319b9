import datetime
import threading
from decimal import Decimal
from unittest.mock import Mock

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.db import connection

from accounts.models import Freelancer
from billing.helpers import bill_freelancer
from billing.models import BillingRun, Invoice, InvoiceLineItem
from billing.tasks import run_billing
from contracts.models import Contract, TimesheetEntry

# --- endpoint: permissions, validation, response shape ---


@pytest.mark.django_db
def test_run_requires_company_admin(freelancer_client):
    resp = freelancer_client.post('/api/billing/runs/', {'month': '2026-04'})
    assert resp.status_code == 403


@pytest.mark.django_db
def test_run_requires_auth(api_client):
    resp = api_client.post('/api/billing/runs/', {'month': '2026-04'})
    assert resp.status_code == 401


@pytest.mark.django_db
def test_run_requires_month(admin_client):
    resp = admin_client.post('/api/billing/runs/', {})
    assert resp.status_code == 400
    assert resp.data['month'][0].code == 'required'


@pytest.mark.django_db
def test_run_rejects_malformed_month(admin_client):
    resp = admin_client.post('/api/billing/runs/', {'month': 'not-a-month'})
    assert resp.status_code == 400
    assert resp.data['month'][0] == 'Expected a YYYY-MM value.'


@pytest.mark.django_db
def test_run_response_shape(admin_client, approved_entry, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        resp = admin_client.post('/api/billing/runs/', {'month': '2026-04'})

    assert resp.status_code == 200
    assert resp.data['status'] == 'completed'
    assert resp.data['invoices_generated'] == 1
    assert resp.data['run_id'] == str(BillingRun.objects.get().id)


# --- run_billing: which entries get billed, idempotency, correction ---


@pytest.mark.django_db
def test_bills_approved_entries_in_month(
    northstar, admin_user, approved_entry, month, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        billing_run = run_billing(company=northstar, month=month, created_by=admin_user)

    assert billing_run.invoices.count() == 1
    invoice = billing_run.invoices.get()
    assert invoice.total_amount == approved_entry.amount
    assert invoice.line_items.count() == 1
    assert invoice.line_items.get().timesheet_entry_id == approved_entry.id


@pytest.mark.django_db
def test_excludes_entries_not_approved(northstar, admin_user, submitted_entry, month):
    billing_run = run_billing(company=northstar, month=month, created_by=admin_user)
    assert billing_run.invoices.count() == 0


@pytest.mark.django_db
def test_excludes_entries_outside_month(northstar, admin_user, active_contract, month):
    TimesheetEntry.objects.create(
        contract=active_contract, date=datetime.date(2026, 3, 31), hours=Decimal('8.0'), status='approved'
    )
    billing_run = run_billing(company=northstar, month=month, created_by=admin_user)
    assert billing_run.invoices.count() == 0


@pytest.mark.django_db
def test_excludes_other_companys_entries(northstar, admin_user, other_contract, month):
    """other_contract belongs to meridian — billing northstar must not touch it."""
    TimesheetEntry.objects.create(
        contract=other_contract, date=datetime.date(2026, 4, 7), hours=Decimal('8.0'), status='approved'
    )
    billing_run = run_billing(company=northstar, month=month, created_by=admin_user)
    assert billing_run.invoices.count() == 0


@pytest.mark.django_db
def test_rerun_is_idempotent(
    northstar, admin_user, approved_entry, month, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        run_billing(company=northstar, month=month, created_by=admin_user)
    with django_capture_on_commit_callbacks(execute=True):
        second_run = run_billing(company=northstar, month=month, created_by=admin_user)

    assert second_run.invoices.count() == 0
    assert Invoice.objects.count() == 1


@pytest.mark.django_db
def test_rerun_bills_newly_approved_entries_as_separate_invoice(
    northstar, admin_user, approved_entry, active_contract, month, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        first_run = run_billing(company=northstar, month=month, created_by=admin_user)

    late_entry = TimesheetEntry.objects.create(
        contract=active_contract, date=datetime.date(2026, 4, 8), hours=Decimal('4.0'), status='approved'
    )
    with django_capture_on_commit_callbacks(execute=True):
        second_run = run_billing(company=northstar, month=month, created_by=admin_user)

    assert second_run.invoices.count() == 1
    first_invoice = first_run.invoices.get()
    second_invoice = second_run.invoices.get()
    assert first_invoice.line_items.count() == 1
    assert second_invoice.line_items.count() == 1
    assert second_invoice.line_items.get().timesheet_entry_id == late_entry.id
    # the original invoice is untouched
    assert first_invoice.line_items.get().timesheet_entry_id == approved_entry.id


@pytest.mark.django_db
def test_one_invoice_per_freelancer(
    northstar, admin_user, active_contract, month, django_capture_on_commit_callbacks
):
    other_user = User.objects.create_user(
        username='other-freelancer@test.test', email='other-freelancer@test.test', password='x'
    )
    other_freelancer = Freelancer.objects.create(user=other_user, name='Other Freelancer')
    other_contract = Contract.objects.create(
        company=northstar,
        freelancer=other_freelancer,
        daily_rate=Decimal('500.00'),
        start_date=datetime.date(2026, 1, 1),
        end_date=datetime.date(2026, 12, 31),
        status='active',
    )
    TimesheetEntry.objects.create(
        contract=active_contract, date=datetime.date(2026, 4, 7), hours=Decimal('8.0'), status='approved'
    )
    TimesheetEntry.objects.create(
        contract=other_contract, date=datetime.date(2026, 4, 7), hours=Decimal('8.0'), status='approved'
    )

    with django_capture_on_commit_callbacks(execute=True):
        billing_run = run_billing(company=northstar, month=month, created_by=admin_user)

    assert billing_run.invoices.count() == 2
    freelancer_ids = set(billing_run.invoices.values_list('freelancer_id', flat=True))
    assert freelancer_ids == {active_contract.freelancer_id, other_freelancer.id}


@pytest.mark.django_db
def test_total_matches_sum_of_rounded_line_items(
    northstar, admin_user, freelancer_user, month, django_capture_on_commit_callbacks
):
    # 4h @ £100.01/day -> 4*100.01/8 = 50.005, which ROUND_HALF_UP rounds to 50.01.
    contract = Contract.objects.create(
        company=northstar,
        freelancer=freelancer_user.freelancer,
        daily_rate=Decimal('100.01'),
        start_date=datetime.date(2026, 1, 1),
        end_date=datetime.date(2026, 12, 31),
        status='active',
    )
    TimesheetEntry.objects.create(
        contract=contract, date=datetime.date(2026, 4, 7), hours=Decimal('4.00'), status='approved'
    )
    billing_run = BillingRun.objects.create(company=northstar, month=month, created_by=admin_user)

    with django_capture_on_commit_callbacks(execute=True):
        invoice = bill_freelancer(northstar, freelancer_user.freelancer.id, month, billing_run)

    line_item = invoice.line_items.get()
    assert line_item.amount == Decimal('50.01')
    assert invoice.total_amount == line_item.amount


# --- email delivery on generation ---


@pytest.mark.django_db
def test_sends_email_to_company_and_freelancer(
    northstar, admin_user, approved_entry, month, django_capture_on_commit_callbacks
):
    billing_run = BillingRun.objects.create(company=northstar, month=month, created_by=admin_user)

    with django_capture_on_commit_callbacks(execute=True):
        invoice = bill_freelancer(northstar, approved_entry.contract.freelancer_id, month, billing_run)

    assert len(mail.outbox) == 1
    sent = mail.outbox[0]
    assert set(sent.to) == {northstar.billing_email, invoice.freelancer.user.email}
    assert invoice.email_status == Invoice.EMAIL_SENT
    assert invoice.email_attempts == 1
    assert invoice.email_sent_at is not None


@pytest.mark.django_db
def test_email_failure_does_not_lose_the_invoice(
    northstar, admin_user, approved_entry, month, django_capture_on_commit_callbacks, monkeypatch
):
    monkeypatch.setattr('billing.helpers.send_mail', Mock(side_effect=Exception('smtp down')))
    billing_run = BillingRun.objects.create(company=northstar, month=month, created_by=admin_user)

    with django_capture_on_commit_callbacks(execute=True):
        invoice = bill_freelancer(northstar, approved_entry.contract.freelancer_id, month, billing_run)

    assert invoice.email_status == Invoice.EMAIL_FAILED
    assert invoice.email_attempts == 1
    assert invoice.email_sent_at is None
    assert len(mail.outbox) == 0


# --- concurrency ---


@pytest.mark.django_db(transaction=True)
def test_concurrent_billing_runs_never_double_bill(northstar, admin_user, approved_entry, month):
    """
    Two real, concurrent billing runs for the same company/month must not
    both bill the same timesheet entry. Needs transaction=True (real commits,
    real locks) and two independent threads (Django DB connections are
    thread-local) to actually exercise SELECT ... FOR UPDATE SKIP LOCKED.
    """
    freelancer_id = approved_entry.contract.freelancer_id
    barrier = threading.Barrier(2)
    results: list[Invoice | None] = []
    errors: list[BaseException] = []

    def attempt():
        try:
            barrier.wait(timeout=5)  # force both threads into the locking query together
            run = BillingRun.objects.create(company=northstar, month=month, created_by=admin_user)
            results.append(bill_freelancer(northstar, freelancer_id, month, run))
        except BaseException as exc:  # surface thread failures on the main thread, not silently
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, errors
    assert len(results) == 2
    # Exactly one thread won the lock and billed the entry; the other found nothing left to lock.
    assert sorted(r is None for r in results) == [False, True]
    assert InvoiceLineItem.objects.filter(timesheet_entry=approved_entry).count() == 1
