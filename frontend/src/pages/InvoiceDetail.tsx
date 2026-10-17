import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { fetchInvoice, resendInvoice } from '../api/billing'
import { ApiError } from '../api/client'
import { StatusBadge } from '../components/StatusBadge'

export default function InvoiceDetail() {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['invoice', id],
    queryFn: () => fetchInvoice(id!),
    retry: false,
  })

  const resendMutation = useMutation({
    mutationFn: () => resendInvoice(id!),
    onSuccess: (invoice) => {
      queryClient.setQueryData(['invoice', id], invoice)
    },
  })

  const isNotFound = isError && error instanceof ApiError && error.status === 404

  if (isLoading) {
    return <p className="text-slate-500">Loading invoice…</p>
  }

  if (isNotFound) {
    return (
      <div>
        <Link to="/billing" className="text-indigo-600 hover:text-indigo-800 text-sm mb-4 inline-block">
          ← Billing
        </Link>
        <div className="bg-white border border-slate-200 rounded-lg px-6 py-12 text-center max-w-md">
          <p className="text-slate-800 font-medium">Invoice not found</p>
          <p className="text-slate-500 text-sm mt-1">
            This invoice doesn't exist yet — billing may not have run for this period.
          </p>
        </div>
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 rounded px-4 py-3 text-sm">
        Failed to load invoice.
      </div>
    )
  }

  const invoice = data

  return (
    <div className="space-y-6">
      <Link to="/billing" className="text-indigo-600 hover:text-indigo-800 text-sm inline-block">
        ← Billing
      </Link>

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">
            Invoice #{invoice.id} — {invoice.freelancer.name} @ {invoice.company.name}
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            {new Date(`${invoice.month}T00:00:00`).toLocaleDateString(undefined, {
              month: 'long',
              year: 'numeric',
            })}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <StatusBadge status={invoice.email_status} />
          {invoice.email_status === 'sent' ? (
            <p className="text-slate-400 text-xs">
              Sent {new Date(invoice.email_sent_at!).toLocaleString()}
            </p>
          ) : (
            <>
              {invoice.email_attempts > 0 && (
                <p className="text-slate-400 text-xs">
                  {invoice.email_attempts} send attempt{invoice.email_attempts === 1 ? '' : 's'}
                </p>
              )}
              <button
                onClick={() => resendMutation.mutate()}
                disabled={resendMutation.isPending}
                className="bg-indigo-600 text-white text-sm px-3 py-1.5 rounded hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {resendMutation.isPending ? 'Resending…' : 'Resend email'}
              </button>
              {resendMutation.isError && (
                <p className="text-red-600 text-xs">Failed to resend. Please try again.</p>
              )}
            </>
          )}
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-200">
            <tr>
              <th className="text-left px-4 py-3 font-medium text-slate-600">Date</th>
              <th className="text-left px-4 py-3 font-medium text-slate-600">Hours</th>
              <th className="text-left px-4 py-3 font-medium text-slate-600">Rate</th>
              <th className="text-right px-4 py-3 font-medium text-slate-600">Amount</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {invoice.line_items.map((li) => (
              <tr key={li.id}>
                <td className="px-4 py-3 text-slate-700">{li.date}</td>
                <td className="px-4 py-3 text-slate-700">{li.hours}h</td>
                <td className="px-4 py-3 text-slate-700">£{Number(li.rate).toFixed(2)}/day</td>
                <td className="px-4 py-3 text-right text-slate-700">£{Number(li.amount).toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot className="bg-slate-50 border-t border-slate-200">
            <tr>
              <td colSpan={3} className="px-4 py-3 font-medium text-slate-700">Total</td>
              <td className="px-4 py-3 text-right font-medium text-slate-900">
                £{Number(invoice.total_amount).toFixed(2)}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  )
}
