import { api, BillingRunResult, Invoice, InvoiceSummary } from './client'

export function runBilling(month: string): Promise<BillingRunResult> {
  return api.post('/api/billing/runs/', { month })
}

export function fetchInvoices(month: string): Promise<InvoiceSummary[]> {
  return api.get(`/api/invoices/?month=${month}`)
}

export function fetchInvoice(id: string | number): Promise<Invoice> {
  return api.get(`/api/invoices/${id}/`)
}

export function resendInvoice(id: string | number): Promise<Invoice> {
  return api.post(`/api/invoices/${id}/resend/`, {})
}
