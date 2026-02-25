'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { cn } from '@/lib/utils/cn'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/input'
import {
  KeyRound,
  ExternalLink,
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  Clock,
  Zap,
  AlertTriangle,
} from 'lucide-react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface DirectLoginFormProps {
  onComplete: () => void
}

interface RegistrySupplier {
  id: string
  name: string
  region: string
  utility_type: string
}

interface SyncStatus {
  last_sync_at: string | null
  next_sync_at: string | null
  last_sync_error: string | null
  rates_found: number
}

interface SyncResult {
  success: boolean
  rates_found: number
  error: string | null
}

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSeconds = Math.floor(diffMs / 1000)
  const diffMinutes = Math.floor(diffSeconds / 60)
  const diffHours = Math.floor(diffMinutes / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffSeconds < 60) return 'just now'
  if (diffMinutes < 60) return `${diffMinutes} minute${diffMinutes !== 1 ? 's' : ''} ago`
  if (diffHours < 24) return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`
  if (diffDays < 30) return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`
  return date.toLocaleDateString()
}

function formatFutureTime(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = date.getTime() - now.getTime()
  const diffMinutes = Math.floor(diffMs / (1000 * 60))
  const diffHours = Math.floor(diffMinutes / 60)

  if (diffMinutes < 1) return 'any moment'
  if (diffMinutes < 60) return `in ${diffMinutes} minute${diffMinutes !== 1 ? 's' : ''}`
  if (diffHours < 24) return `in ${diffHours} hour${diffHours !== 1 ? 's' : ''}`
  return date.toLocaleDateString()
}

export function DirectLoginForm({ onComplete }: DirectLoginFormProps) {
  const [suppliers, setSuppliers] = useState<RegistrySupplier[]>([])
  const [loadingSuppliers, setLoadingSuppliers] = useState(true)
  const [selectedSupplierId, setSelectedSupplierId] = useState('')
  const [consentChecked, setConsentChecked] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [connectionId, setConnectionId] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  // Sync state
  const [syncing, setSyncing] = useState(false)
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null)
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null)
  const [syncError, setSyncError] = useState<string | null>(null)

  useEffect(() => {
    async function loadSuppliers() {
      try {
        const res = await fetch(`${API_BASE}/api/v1/suppliers/registry`, {
          credentials: 'include',
        })
        if (res.ok) {
          const data = await res.json()
          setSuppliers(data.suppliers || data || [])
        }
      } catch {
        // Supplier registry unavailable - form still usable with manual input
      } finally {
        setLoadingSuppliers(false)
      }
    }
    loadSuppliers()
  }, [])

  const fetchSyncStatus = useCallback(async (connId: string) => {
    try {
      const res = await fetch(
        `${API_BASE}/api/v1/connections/${connId}/sync/status`,
        { credentials: 'include' }
      )
      if (res.ok) {
        const data: SyncStatus = await res.json()
        setSyncStatus(data)
      }
    } catch {
      // Silently fail - sync status is supplementary info
    }
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!selectedSupplierId) {
      setError('Please select a utility provider')
      return
    }
    if (!consentChecked) {
      setError('You must consent to data access before connecting')
      return
    }

    try {
      setSubmitting(true)
      setError(null)

      const res = await fetch(`${API_BASE}/api/v1/connections/direct`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          supplier_id: selectedSupplierId,
          oauth_provider: 'utility_api',
          consent: true,
        }),
      })

      if (res.ok) {
        const data = await res.json()
        if (data.redirect_url) {
          window.location.href = data.redirect_url
          return
        }
        const connId = data.id || data.connection_id
        setConnectionId(connId)
        setSuccess(true)
        // Fetch initial sync status
        fetchSyncStatus(connId)
      } else if (res.status === 403) {
        setError(
          'Direct connections are available on Pro and Business plans. Please upgrade to continue.'
        )
      } else {
        const data = await res.json().catch(() => null)
        setError(
          data?.detail || 'Failed to initiate connection. Please try again.'
        )
      }
    } catch {
      setError('Network error. Please check your connection and try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleSyncNow = async () => {
    if (!connectionId) return

    try {
      setSyncing(true)
      setSyncError(null)
      setSyncResult(null)

      const res = await fetch(
        `${API_BASE}/api/v1/connections/${connectionId}/sync`,
        {
          method: 'POST',
          credentials: 'include',
        }
      )

      if (res.ok) {
        const data = await res.json()
        setSyncResult({
          success: true,
          rates_found: data.rates_found ?? data.new_rates ?? 0,
          error: null,
        })
        // Refresh sync status
        fetchSyncStatus(connectionId)
      } else if (res.status === 403) {
        setSyncError(
          'Syncing requires a Pro or Business plan. Please upgrade to continue.'
        )
      } else {
        const data = await res.json().catch(() => null)
        setSyncError(data?.detail || 'Sync failed. Please try again.')
        setSyncResult({
          success: false,
          rates_found: 0,
          error: data?.detail || 'Sync failed',
        })
      }
    } catch {
      setSyncError('Network error. Please try again.')
    } finally {
      setSyncing(false)
    }
  }

  // Post-connection success state with sync controls
  if (success && connectionId) {
    return (
      <Card padding="lg">
        <div className="flex items-center gap-3 mb-6">
          <CheckCircle2 className="h-6 w-6 text-success-500" />
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              Connection Established
            </h2>
            <p className="text-sm text-gray-500">
              Your utility account is linked. Sync your data to get started.
            </p>
          </div>
        </div>

        <div className="space-y-5">
          {/* Sync status info */}
          {syncStatus && (
            <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 space-y-2">
              {syncStatus.last_sync_at && (
                <div className="flex items-center gap-2 text-sm">
                  <Clock className="h-4 w-4 text-gray-400" />
                  <span className="text-gray-600">Last synced:</span>
                  <span className="font-medium text-gray-900">
                    {formatRelativeTime(syncStatus.last_sync_at)}
                  </span>
                </div>
              )}
              {syncStatus.next_sync_at && (
                <div className="flex items-center gap-2 text-sm">
                  <RefreshCw className="h-4 w-4 text-gray-400" />
                  <span className="text-gray-600">Next sync:</span>
                  <span className="font-medium text-gray-900">
                    {formatFutureTime(syncStatus.next_sync_at)}
                  </span>
                </div>
              )}
              {syncStatus.last_sync_error && (
                <div className="flex items-center gap-2 text-sm">
                  <AlertTriangle className="h-4 w-4 text-warning-500" />
                  <span className="text-warning-700">
                    {syncStatus.last_sync_error}
                  </span>
                </div>
              )}
              {syncStatus.rates_found > 0 && (
                <div className="flex items-center gap-2 text-sm">
                  <Zap className="h-4 w-4 text-primary-500" />
                  <span className="text-gray-600">Rates on file:</span>
                  <span className="font-medium text-gray-900">
                    {syncStatus.rates_found}
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Sync result feedback */}
          {syncResult && syncResult.success && (
            <div className="flex items-center gap-2 rounded-lg border border-success-200 bg-success-50 p-3">
              <CheckCircle2 className="h-5 w-5 text-success-500 shrink-0" />
              <div>
                <p className="text-sm font-medium text-success-700">
                  Sync completed
                </p>
                <p className="text-xs text-success-600">
                  {syncResult.rates_found > 0
                    ? `Found ${syncResult.rates_found} new rate${syncResult.rates_found !== 1 ? 's' : ''}`
                    : 'No new rates found. Your data is up to date.'}
                </p>
              </div>
            </div>
          )}

          {/* Sync error */}
          {syncError && (
            <div className="flex items-start gap-2 rounded-lg border border-danger-200 bg-danger-50 p-3">
              <AlertCircle className="mt-0.5 h-4 w-4 text-danger-500 shrink-0" />
              <p className="text-sm text-danger-700">{syncError}</p>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-3">
            <Button
              variant="primary"
              className="flex-1"
              onClick={handleSyncNow}
              loading={syncing}
            >
              <RefreshCw className="h-4 w-4" />
              {syncing ? 'Syncing...' : 'Sync Now'}
            </Button>
            <Button variant="outline" onClick={onComplete}>
              Done
            </Button>
          </div>
        </div>
      </Card>
    )
  }

  return (
    <Card padding="lg">
      <div className="flex items-center gap-3 mb-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary-100">
          <KeyRound className="h-5 w-5 text-primary-600" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            Connect Utility Account
          </h2>
          <p className="text-sm text-gray-500">
            Link your provider account to automatically sync rates and billing
            data
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Supplier selector */}
        <div>
          <label
            htmlFor="supplier-select"
            className="mb-1 block text-sm font-medium text-gray-700"
          >
            Utility Provider
          </label>
          {loadingSuppliers ? (
            <div className="h-10 w-full animate-pulse rounded-lg bg-gray-100" />
          ) : (
            <select
              id="supplier-select"
              value={selectedSupplierId}
              onChange={(e) => {
                setSelectedSupplierId(e.target.value)
                setError(null)
              }}
              className={cn(
                'block w-full rounded-lg border border-gray-300 bg-white px-3 py-2',
                'text-gray-900 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500',
                'disabled:cursor-not-allowed disabled:bg-gray-50'
              )}
            >
              <option value="">Select your utility provider...</option>
              {suppliers.map((supplier) => (
                <option key={supplier.id} value={supplier.id}>
                  {supplier.name}
                </option>
              ))}
            </select>
          )}
        </div>

        {/* OAuth provider info */}
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
          <div className="flex items-start gap-3">
            <ExternalLink className="mt-0.5 h-4 w-4 text-gray-400 shrink-0" />
            <div>
              <p className="text-sm font-medium text-gray-700">
                Powered by UtilityAPI
              </p>
              <p className="mt-1 text-xs text-gray-500">
                You will be redirected to securely authorize read-only access to
                your utility account data. We never store your login
                credentials.
              </p>
            </div>
          </div>
        </div>

        {/* Consent */}
        <Checkbox
          label="I consent to Electricity Optimizer accessing my utility billing data for rate comparison and optimization purposes"
          checked={consentChecked}
          onChange={(e) => {
            setConsentChecked(e.target.checked)
            setError(null)
          }}
        />

        {/* Error */}
        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-danger-200 bg-danger-50 p-3">
            <AlertCircle className="mt-0.5 h-4 w-4 text-danger-500 shrink-0" />
            <p className="text-sm text-danger-700">{error}</p>
          </div>
        )}

        {/* Submit */}
        <Button
          type="submit"
          variant="primary"
          className="w-full"
          loading={submitting}
          disabled={!selectedSupplierId || !consentChecked}
        >
          <KeyRound className="h-4 w-4" />
          Connect Utility Account
        </Button>
      </form>
    </Card>
  )
}
