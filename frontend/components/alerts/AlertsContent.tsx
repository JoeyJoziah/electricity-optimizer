'use client'

import React, { useState } from 'react'
import Link from 'next/link'
import { Header } from '@/components/layout/Header'
import { useAlerts, useAlertHistory, useDeleteAlert, useUpdateAlert } from '@/lib/hooks/useAlerts'
import { AlertForm } from '@/components/alerts/AlertForm'
import { Skeleton, TableRowSkeleton } from '@/components/ui/skeleton'
import { STATE_LABELS } from '@/lib/constants/regions'
import { Bell, Plus, Trash2, ToggleLeft, ToggleRight, ChevronLeft, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import type { Alert, AlertHistoryItem } from '@/lib/api/alerts'

type Tab = 'alerts' | 'history'

function AlertTypeLabel({ type }: { type: string }) {
  const config: Record<string, { label: string; className: string }> = {
    price_drop: { label: 'Price Drop', className: 'bg-success-50 text-success-700' },
    price_spike: { label: 'Price Spike', className: 'bg-danger-50 text-danger-700' },
    optimal_window: { label: 'Optimal Window', className: 'bg-primary-50 text-primary-700' },
  }
  const c = config[type] ?? { label: type, className: 'bg-gray-50 text-gray-700' }
  return (
    <span className={cn('inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium', c.className)}>
      {c.label}
    </span>
  )
}

function formatRegion(region: string): string {
  return STATE_LABELS[region] ?? region.replace('us_', '').toUpperCase()
}

function formatPrice(value: number | null): string {
  if (value === null) return '--'
  return `$${value.toFixed(4)}/kWh`
}

function formatDate(iso: string | null): string {
  if (!iso) return '--'
  return new Date(iso).toLocaleString()
}

// ---------------------------------------------------------------------------
// My Alerts Tab
// ---------------------------------------------------------------------------

function MyAlertsTab() {
  const { data, isLoading, isError } = useAlerts()
  const deleteMutation = useDeleteAlert()
  const updateMutation = useUpdateAlert()
  const [showForm, setShowForm] = useState(false)

  const handleToggleActive = (alert: Alert) => {
    updateMutation.mutate({ id: alert.id, body: { is_active: !alert.is_active } })
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="rounded-xl border border-gray-200 bg-white p-4">
            <Skeleton variant="text" className="mb-2 h-5 w-1/3" />
            <Skeleton variant="text" className="h-4 w-2/3" />
          </div>
        ))}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="rounded-xl border border-danger-200 bg-danger-50 p-6 text-center">
        <p className="text-sm text-danger-700">Failed to load alerts. Please try again.</p>
      </div>
    )
  }

  const alerts = data?.alerts ?? []

  return (
    <div className="space-y-4">
      {/* Add Alert button + free-tier note */}
      <div className="flex items-center justify-between">
        {alerts.length >= 1 ? (
          <p className="text-xs text-gray-500" data-testid="free-tier-note">
            Free plan: 1 alert.{' '}
            <Link href="/pricing" className="text-primary-600 hover:underline">
              Upgrade for unlimited
            </Link>
          </p>
        ) : (
          <div />
        )}
        <button
          onClick={() => setShowForm(!showForm)}
          className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 transition-colors"
        >
          <Plus className="h-4 w-4" />
          {showForm ? 'Cancel' : 'Add Alert'}
        </button>
      </div>

      {/* Inline form */}
      {showForm && (
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <AlertForm onSuccess={() => setShowForm(false)} />
        </div>
      )}

      {/* Alerts list */}
      {alerts.length === 0 && !showForm ? (
        <div className="rounded-xl border border-gray-200 bg-white px-6 py-12 text-center" data-testid="empty-alerts">
          <Bell className="mx-auto h-12 w-12 text-gray-300" />
          <h3 className="mt-4 text-sm font-medium text-gray-900">No alerts configured yet</h3>
          <p className="mt-1 text-sm text-gray-500">
            Create your first alert to get notified about price changes.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {alerts.map((alert) => (
            <div
              key={alert.id}
              className={cn(
                'rounded-xl border bg-white p-4 transition-colors',
                alert.is_active ? 'border-gray-200' : 'border-gray-100 opacity-60'
              )}
              data-testid="alert-card"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-gray-900">
                      {formatRegion(alert.region)}
                    </span>
                    {alert.is_active ? (
                      <span className="inline-flex items-center rounded-full bg-success-50 px-2 py-0.5 text-xs font-medium text-success-700">
                        Active
                      </span>
                    ) : (
                      <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
                        Paused
                      </span>
                    )}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-3 text-sm text-gray-500">
                    {alert.price_below !== null && (
                      <span>Below: {formatPrice(alert.price_below)}</span>
                    )}
                    {alert.price_above !== null && (
                      <span>Above: {formatPrice(alert.price_above)}</span>
                    )}
                    {alert.notify_optimal_windows && (
                      <span>Optimal windows</span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {/* Toggle active */}
                  <button
                    onClick={() => handleToggleActive(alert)}
                    className="rounded-md p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
                    aria-label={alert.is_active ? 'Pause alert' : 'Activate alert'}
                    data-testid="toggle-alert"
                  >
                    {alert.is_active ? (
                      <ToggleRight className="h-5 w-5 text-success-500" />
                    ) : (
                      <ToggleLeft className="h-5 w-5" />
                    )}
                  </button>
                  {/* Delete */}
                  <button
                    onClick={() => deleteMutation.mutate(alert.id)}
                    className="rounded-md p-1.5 text-gray-400 hover:bg-danger-50 hover:text-danger-600 transition-colors"
                    aria-label="Delete alert"
                    data-testid="delete-alert"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// History Tab
// ---------------------------------------------------------------------------

function HistoryTab() {
  const [page, setPage] = useState(1)
  const { data, isLoading, isError } = useAlertHistory(page)

  if (isLoading) {
    return (
      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50">
              <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Type</th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Region</th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Price</th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Threshold</th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Triggered</th>
            </tr>
          </thead>
          <tbody>
            {[1, 2, 3].map((i) => (
              <TableRowSkeleton key={i} columns={5} />
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="rounded-xl border border-danger-200 bg-danger-50 p-6 text-center">
        <p className="text-sm text-danger-700">Failed to load alert history. Please try again.</p>
      </div>
    )
  }

  const items: AlertHistoryItem[] = data?.items ?? []
  const totalPages = data?.pages ?? 1

  if (items.length === 0 && page === 1) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white px-6 py-12 text-center" data-testid="empty-history">
        <Bell className="mx-auto h-12 w-12 text-gray-300" />
        <h3 className="mt-4 text-sm font-medium text-gray-900">No alert history</h3>
        <p className="mt-1 text-sm text-gray-500">
          Triggered alerts will appear here once your alert conditions are met.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50">
              <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Type</th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Region</th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Price</th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Threshold</th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Triggered</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {items.map((item) => (
              <tr key={item.id} className="hover:bg-gray-50 transition-colors" data-testid="history-row">
                <td className="px-4 py-3">
                  <AlertTypeLabel type={item.alert_type} />
                </td>
                <td className="px-4 py-3 text-sm text-gray-900">{formatRegion(item.region)}</td>
                <td className="px-4 py-3 text-sm text-gray-900">{formatPrice(item.current_price)}</td>
                <td className="px-4 py-3 text-sm text-gray-500">{formatPrice(item.threshold)}</td>
                <td className="px-4 py-3 text-sm text-gray-500">{formatDate(item.triggered_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-gray-500">
            Page {page} of {totalPages} ({data?.total ?? 0} results)
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="inline-flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
              aria-label="Previous page"
            >
              <ChevronLeft className="h-4 w-4" />
              Previous
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="inline-flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
              aria-label="Next page"
            >
              Next
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function AlertsContent() {
  const [activeTab, setActiveTab] = useState<Tab>('alerts')

  return (
    <>
      <Header title="Alerts" />
      <div className="p-4 lg:p-6">
        {/* Tabs */}
        <div className="mb-6 border-b border-gray-200">
          <nav className="-mb-px flex gap-6" aria-label="Alert tabs">
            <button
              onClick={() => setActiveTab('alerts')}
              className={cn(
                'whitespace-nowrap border-b-2 pb-3 text-sm font-medium transition-colors',
                activeTab === 'alerts'
                  ? 'border-primary-600 text-primary-600'
                  : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'
              )}
            >
              My Alerts
            </button>
            <button
              onClick={() => setActiveTab('history')}
              className={cn(
                'whitespace-nowrap border-b-2 pb-3 text-sm font-medium transition-colors',
                activeTab === 'history'
                  ? 'border-primary-600 text-primary-600'
                  : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'
              )}
            >
              History
            </button>
          </nav>
        </div>

        {/* Tab content */}
        {activeTab === 'alerts' ? <MyAlertsTab /> : <HistoryTab />}
      </div>
    </>
  )
}
