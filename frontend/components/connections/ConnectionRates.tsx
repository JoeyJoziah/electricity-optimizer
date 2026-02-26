'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { cn } from '@/lib/utils/cn'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  TrendingUp,
  Calendar,
  Zap,
  Upload,
  ArrowLeft,
  Loader2,
  AlertCircle,
  RefreshCw,
} from 'lucide-react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface ConnectionRate {
  id: string
  rate_per_kwh: number
  currency: string
  period_start: string
  period_end: string
  usage_kwh: number | null
  amount: number | null
  source: string
  extracted_at: string
}

interface ConnectionRatesProps {
  connectionId: string
  connectionMethod: string
  supplierName: string | null
  onBack: () => void
  onUploadAnother?: () => void
}

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function formatCurrency(amount: number, currency: string): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency || 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(amount)
}

function formatRate(rate: number): string {
  return `${(rate * 100).toFixed(2)} c/kWh`
}

export function ConnectionRates({
  connectionId,
  connectionMethod,
  supplierName,
  onBack,
  onUploadAnother,
}: ConnectionRatesProps) {
  const [rates, setRates] = useState<ConnectionRate[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchRates = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const res = await fetch(
        `${API_BASE}/api/v1/connections/${connectionId}/rates`,
        { credentials: 'include' }
      )
      if (res.ok) {
        const data = await res.json()
        setRates(data.rates || [])
      } else if (res.status === 403) {
        setError('upgrade')
      } else {
        setError('Failed to load rates')
      }
    } catch {
      setError('Failed to load rates. Please check your connection.')
    } finally {
      setLoading(false)
    }
  }, [connectionId])

  useEffect(() => {
    fetchRates()
  }, [fetchRates])

  const mostRecentRate = rates.length > 0 ? rates[0] : null

  if (error === 'upgrade') {
    return (
      <Card padding="lg" className="text-center">
        <Zap className="mx-auto h-12 w-12 text-gray-300" aria-hidden="true" />
        <h3 className="mt-4 text-lg font-semibold text-gray-900">
          Upgrade Required
        </h3>
        <p className="mt-2 text-sm text-gray-500">
          Rate history is available on Pro and Business plans.
        </p>
        <a
          href="/pricing"
          className="mt-6 inline-block rounded-lg bg-primary-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-primary-700 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
        >
          View Plans
        </a>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 rounded"
            aria-label="Back to connections"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              {supplierName || 'Connection'} Rates
            </h2>
            <p className="text-sm text-gray-500" aria-live="polite">
              {rates.length} rate{rates.length !== 1 ? 's' : ''} extracted
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={fetchRates} aria-label="Refresh rates">
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
          {connectionMethod === 'bill_upload' && onUploadAnother && (
            <Button variant="outline" size="sm" onClick={onUploadAnother}>
              <Upload className="h-4 w-4" />
              Upload Another Bill
            </Button>
          )}
        </div>
      </div>

      {/* Current rate highlight */}
      {mostRecentRate && (
        <Card variant="bordered" padding="lg" className="bg-primary-50 border-primary-200">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-primary-700">
                Current Rate
              </p>
              <p className="mt-1 text-3xl font-bold text-primary-900">
                {formatRate(mostRecentRate.rate_per_kwh)}
              </p>
              <p className="mt-1 text-xs text-primary-600">
                {formatDate(mostRecentRate.period_start)} &mdash;{' '}
                {formatDate(mostRecentRate.period_end)}
              </p>
            </div>
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary-100">
              <TrendingUp className="h-7 w-7 text-primary-600" aria-hidden="true" />
            </div>
          </div>
          {(mostRecentRate.usage_kwh !== null || mostRecentRate.amount !== null) && (
            <div className="mt-4 flex items-center gap-6 border-t border-primary-200 pt-4">
              {mostRecentRate.usage_kwh !== null && (
                <div>
                  <p className="text-xs text-primary-600">Usage</p>
                  <p className="text-sm font-semibold text-primary-900">
                    {mostRecentRate.usage_kwh.toLocaleString()} kWh
                  </p>
                </div>
              )}
              {mostRecentRate.amount !== null && (
                <div>
                  <p className="text-xs text-primary-600">Amount</p>
                  <p className="text-sm font-semibold text-primary-900">
                    {formatCurrency(mostRecentRate.amount, mostRecentRate.currency)}
                  </p>
                </div>
              )}
            </div>
          )}
        </Card>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12" role="status">
          <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
          <span className="ml-2 text-sm text-gray-500">Loading rates...</span>
        </div>
      )}

      {/* Error */}
      {error && error !== 'upgrade' && (
        <div className="flex items-start gap-2 rounded-lg border border-danger-200 bg-danger-50 p-4" role="alert">
          <AlertCircle className="mt-0.5 h-4 w-4 text-danger-500 shrink-0" aria-hidden="true" />
          <div>
            <p className="text-sm text-danger-700">{error}</p>
            <button
              onClick={fetchRates}
              className="mt-1 text-sm font-medium text-danger-600 hover:text-danger-800 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger-500 focus-visible:ring-offset-2 rounded"
              aria-label="Retry loading rates"
            >
              Try again
            </button>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && rates.length === 0 && (
        <Card padding="lg" className="text-center">
          <Calendar className="mx-auto h-12 w-12 text-gray-300" aria-hidden="true" />
          <h3 className="mt-4 text-lg font-semibold text-gray-900">
            No Rates Yet
          </h3>
          <p className="mt-2 text-sm text-gray-500">
            {connectionMethod === 'bill_upload'
              ? 'Upload a bill to extract rate data.'
              : 'Rate data will appear here after a successful sync.'}
          </p>
          {connectionMethod === 'bill_upload' && onUploadAnother && (
            <Button variant="primary" className="mt-6" onClick={onUploadAnother}>
              <Upload className="h-4 w-4" />
              Upload a Bill
            </Button>
          )}
        </Card>
      )}

      {/* Rate table */}
      {!loading && rates.length > 0 && (
        <Card variant="bordered" padding="none">
          <div className="overflow-x-auto">
            <table className="w-full" aria-label="Extracted rate history">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Period
                  </th>
                  <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Rate
                  </th>
                  <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Usage
                  </th>
                  <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Amount
                  </th>
                  <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Source
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {rates.map((rate, index) => (
                  <tr
                    key={rate.id}
                    className={cn(
                      'transition-colors hover:bg-gray-50',
                      index === 0 && 'bg-primary-50/50'
                    )}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-gray-900">
                          {formatDate(rate.period_start)} &mdash;{' '}
                          {formatDate(rate.period_end)}
                        </span>
                        {index === 0 && (
                          <Badge variant="info" size="sm">
                            Latest
                          </Badge>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm font-semibold text-gray-900">
                        {formatRate(rate.rate_per_kwh)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm text-gray-700">
                        {rate.usage_kwh !== null
                          ? `${rate.usage_kwh.toLocaleString()} kWh`
                          : '\u2014'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm text-gray-700">
                        {rate.amount !== null
                          ? formatCurrency(rate.amount, rate.currency)
                          : '\u2014'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <Badge
                        variant={
                          rate.source === 'bill_upload'
                            ? 'warning'
                            : rate.source === 'direct_sync'
                              ? 'success'
                              : 'default'
                        }
                        size="sm"
                      >
                        {rate.source === 'bill_upload'
                          ? 'Upload'
                          : rate.source === 'direct_sync'
                            ? 'Sync'
                            : rate.source}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}
