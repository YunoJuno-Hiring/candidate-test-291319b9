# Candidate Notes

## What & why

Picked Task B. Weighed A/B/C first — B is the most backend-depth task (data modelling, idempotency, transactions, affects all freelancers - high user-impact), frontend already wired, best use of time.

## Implementation notes

- Setup: IDE, env, docker-compose. Read through pyproject.toml/compose/existing billing+contracts code before writing anything.
- Used LLM as a rubber duck on the design before coding:
  - Invoices can't be unique per company/freelancer/month — a timesheet entry approved after an invoice is issued can't be retroactively added (invoices are immutable once sent). Re-running billing for a month creates a new invoice for newly-eligible entries instead. Real idempotency guard is `InvoiceLineItem.timesheet_entry` being a OneToOne — an entry can never be billed twice.
  - Track email send attempts/status on the invoice so a failed send never loses the invoice.
  - Unified the `hours/8 * daily_rate` calc (duplicated in frontend) into one backend `TimesheetEntry.amount` property.
- LLM did first implementation pass, then several review rounds together: query perf (select/prefetch_related), style nits, typing, concurrency (switched from catch-IntegrityError to `SELECT FOR UPDATE SKIP LOCKED`), shared `IsCompanyAdmin` permission + `get_object_or_404` to cut repeated boilerplate, and a custom `MonthField` serializer (replaced hand-rolled parsing) that normalises to the last day of the period, not the first.
- Tests: pytest, matched existing conftest fixture and layout conventions. Covered idempotency, late-approval correction, cross-company isolation, decimal rounding, email-failure-doesn't-lose-invoice, and real concurrent locking — two threads/connections racing on the same entry via `django_db(transaction=True)` + `threading.Barrier`. TDD'd that one: removed `select_for_update` to confirm it fails (consistent `IntegrityError`), restored it, confirmed it passes.
- Frontend: invoice list page (number/company/freelancer/status columns), invoice detail page (line items, resend action — hides once sent, shows "Sent {datetime}" instead).

## Workflow

Claude Code, discuss-then-implement loop rather than one-shot — design out loud, push back on edge cases (e.g. the invoice-uniqueness point above came from me rejecting its first "additive re-run" suggestion), implement, then a pre-PR review pass to catch redundant code/missed query opts/etc. Useful for pressure-testing decisions before they're locked into code.

## Next steps (extra time / real-world production implementation)

- Draft flow for invoices (create and approve later)
- Show unbilled-but-approved entries in the UI so they don't get missed.
- UUIDs instead of PKs for invoice (and other) ids — prevent enumeration.
- Real invoice numbers (unique, incrementing), decoupled from DB pk.
- Async email send (Celery/RQ) instead of `transaction.on_commit` + sync send — the on_commit hook is already the right place for this. Would also change resend's contract to `202 Accepted` (pending) rather than the current `200` with a final sent/failed status.
- Relative imports (`from .models import x`) → absolute (`from app.models import x`).
- Pre-commit/lint (black/ruff) — none configured currently.
- Pagination on list endpoints.
- Admin `autocomplete_fields` instead of `raw_id_fields` — needs `search_fields` added to Company/Freelancer/User admin, didn't want to touch outside this task's scope.
- More thorough exception handling in invoice generation/sending
