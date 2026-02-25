'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { cn } from '@/lib/utils/cn'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/input'
import {
  Mail,
  AlertCircle,
  CheckCircle,
  Loader2,
  Search,
  FileText,
} from 'lucide-react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface EmailConnectionFlowProps {
  onComplete: () => void
}

type EmailProvider = 'gmail' | 'outlook'

interface ScanResult {
  total_emails_scanned: number
  utility_bills_found: number
  bills: UtilityBill[]
}

interface UtilityBill {
  subject: string
  date?: string
  sender?: string
  amount?: number
}

export function EmailConnectionFlow({ onComplete }: EmailConnectionFlowProps) {
  const [selectedProvider, setSelectedProvider] = useState<EmailProvider | null>(
    null
  )
  const [consentChecked, setConsentChecked] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [connecting, setConnecting] = useState(false)

  // Post-OAuth connected state
  const [connectionId, setConnectionId] = useState<string | null>(null)
  const [connected, setConnected] = useState(false)

  // Scan state
  const [scanning, setScanning] = useState(false)
  const [scanResult, setScanResult] = useState<ScanResult | null>(null)
  const [scanError, setScanError] = useState<string | null>(null)

  // Check URL for ?connected=CONNECTION_ID on mount
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const connectedId = params.get('connected')
    if (connectedId) {
      setConnectionId(connectedId)
      setConnected(true)
    }
  }, [])

  const handleConnect = useCallback(async () => {
    if (!selectedProvider) {
      setError('Please select an email provider')
      return
    }
    if (!consentChecked) {
      setError('You must consent to email scanning before connecting')
      return
    }

    try {
      setConnecting(true)
      setError(null)

      const res = await fetch(`${API_BASE}/api/v1/connections/email`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: selectedProvider, consent_given: true }),
      })

      if (res.ok) {
        const data = await res.json()
        if (data.redirect_url) {
          // Full page redirect for OAuth flow
          window.location.href = data.redirect_url
          return
        }
        // Fallback: if no redirect URL, treat as direct connection
        setConnectionId(data.connection_id || data.id)
        setConnected(true)
      } else if (res.status === 403) {
        setError(
          'Email connections are available on Pro and Business plans. Please upgrade to continue.'
        )
      } else {
        const data = await res.json().catch(() => null)
        setError(
          data?.detail || 'Failed to initiate email connection. Please try again.'
        )
      }
    } catch {
      setError('Network error. Please check your connection and try again.')
    } finally {
      setConnecting(false)
    }
  }, [selectedProvider, consentChecked])

  const handleScanInbox = useCallback(async () => {
    if (!connectionId) return

    try {
      setScanning(true)
      setScanError(null)
      setScanResult(null)

      const res = await fetch(
        `${API_BASE}/api/v1/connections/email/${connectionId}/scan`,
        {
          method: 'POST',
          credentials: 'include',
        }
      )

      if (res.ok) {
        const data: ScanResult = await res.json()
        setScanResult(data)
      } else if (res.status === 403) {
        setScanError(
          'Inbox scanning requires a Pro or Business plan. Please upgrade to continue.'
        )
      } else {
        const data = await res.json().catch(() => null)
        setScanError(data?.detail || 'Inbox scan failed. Please try again.')
      }
    } catch {
      setScanError('Network error. Please check your connection and try again.')
    } finally {
      setScanning(false)
    }
  }, [connectionId])

  // Post-OAuth connected state with scan controls
  if (connected && connectionId) {
    return (
      <Card padding="lg">
        <div className="flex items-center gap-3 mb-6">
          <CheckCircle className="h-6 w-6 text-success-500" />
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              Email Connected Successfully
            </h2>
            <p className="text-sm text-gray-500">
              Your email account is linked. Scan your inbox to find utility bills.
            </p>
          </div>
        </div>

        <div className="space-y-5">
          {/* Scan result feedback */}
          {scanResult && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 rounded-lg border border-success-200 bg-success-50 p-3">
                <CheckCircle className="h-5 w-5 text-success-500 shrink-0" />
                <div>
                  <p className="text-sm font-medium text-success-700">
                    Scan complete
                  </p>
                  <p className="text-xs text-success-600">
                    Scanned {scanResult.total_emails_scanned} email
                    {scanResult.total_emails_scanned !== 1 ? 's' : ''} and found{' '}
                    {scanResult.utility_bills_found} utility bill
                    {scanResult.utility_bills_found !== 1 ? 's' : ''}
                  </p>
                </div>
              </div>

              {/* Bill list */}
              {scanResult.bills.length > 0 && (
                <div className="rounded-lg border border-gray-200 divide-y divide-gray-100">
                  {scanResult.bills.map((bill, index) => (
                    <div
                      key={index}
                      className="flex items-start gap-3 p-3"
                    >
                      <FileText className="mt-0.5 h-4 w-4 text-gray-400 shrink-0" />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-gray-900 truncate">
                          {bill.subject}
                        </p>
                        <div className="flex items-center gap-3 mt-0.5">
                          {bill.sender && (
                            <p className="text-xs text-gray-500 truncate">
                              {bill.sender}
                            </p>
                          )}
                          {bill.date && (
                            <p className="text-xs text-gray-400">
                              {bill.date}
                            </p>
                          )}
                          {bill.amount != null && (
                            <p className="text-xs font-medium text-gray-700">
                              ${bill.amount.toFixed(2)}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {scanResult.utility_bills_found === 0 && (
                <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 text-center">
                  <p className="text-sm text-gray-500">
                    No utility bills found in your inbox. Try connecting a
                    different email account or upload bills manually.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Scan error */}
          {scanError && (
            <div className="flex items-start gap-2 rounded-lg border border-danger-200 bg-danger-50 p-3">
              <AlertCircle className="mt-0.5 h-4 w-4 text-danger-500 shrink-0" />
              <p className="text-sm text-danger-700">{scanError}</p>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-3">
            <Button
              variant="primary"
              className="flex-1"
              onClick={handleScanInbox}
              loading={scanning}
            >
              <Search className="h-4 w-4" />
              {scanning ? 'Scanning...' : scanResult ? 'Scan Again' : 'Scan Inbox'}
            </Button>
            <Button variant="outline" onClick={onComplete}>
              Done
            </Button>
          </div>
        </div>
      </Card>
    )
  }

  // Connecting state (API call in progress, waiting for redirect URL)
  if (connecting) {
    return (
      <Card className="p-8 text-center">
        <Loader2 className="mx-auto h-12 w-12 text-primary-400 animate-spin" />
        <h3 className="mt-4 text-lg font-semibold text-gray-900">
          Connecting...
        </h3>
        <p className="mt-2 text-sm text-gray-500">
          Setting up your email connection. You will be redirected to authorize
          access shortly.
        </p>
      </Card>
    )
  }

  return (
    <Card padding="lg">
      <div className="flex items-center gap-3 mb-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-success-100">
          <Mail className="h-5 w-5 text-success-600" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            Connect Email Inbox
          </h2>
          <p className="text-sm text-gray-500">
            We will scan your inbox for utility bills and extract rate data automatically
          </p>
        </div>
      </div>

      <div className="space-y-6">
        {/* Provider selector */}
        <div>
          <label className="mb-3 block text-sm font-medium text-gray-700">
            Select your email provider
          </label>
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => {
                setSelectedProvider('gmail')
                setError(null)
              }}
              className={cn(
                'flex items-center gap-3 rounded-xl border p-4 transition-all',
                'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
                selectedProvider === 'gmail'
                  ? 'border-primary-500 bg-primary-50 shadow-sm'
                  : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm'
              )}
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-red-100">
                <Mail className="h-5 w-5 text-red-600" />
              </div>
              <div className="text-left">
                <p className="text-sm font-medium text-gray-900">Gmail</p>
                <p className="text-xs text-gray-500">Google Account</p>
              </div>
            </button>

            <button
              type="button"
              onClick={() => {
                setSelectedProvider('outlook')
                setError(null)
              }}
              className={cn(
                'flex items-center gap-3 rounded-xl border p-4 transition-all',
                'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
                selectedProvider === 'outlook'
                  ? 'border-primary-500 bg-primary-50 shadow-sm'
                  : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm'
              )}
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-100">
                <Mail className="h-5 w-5 text-blue-600" />
              </div>
              <div className="text-left">
                <p className="text-sm font-medium text-gray-900">Outlook</p>
                <p className="text-xs text-gray-500">Microsoft Account</p>
              </div>
            </button>
          </div>
        </div>

        {/* Privacy info */}
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
          <div className="flex items-start gap-3">
            <Mail className="mt-0.5 h-4 w-4 text-gray-400 shrink-0" />
            <div>
              <p className="text-sm font-medium text-gray-700">
                Privacy-first scanning
              </p>
              <p className="mt-1 text-xs text-gray-500">
                We only scan for utility-related emails. Your personal emails
                are never read, stored, or shared. You can revoke access at any time.
              </p>
            </div>
          </div>
        </div>

        {/* Consent */}
        <Checkbox
          label="I consent to Electricity Optimizer scanning my inbox for utility-related emails only"
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
        <div className="flex items-center gap-3">
          <Button
            variant="primary"
            className="flex-1"
            onClick={handleConnect}
            disabled={!selectedProvider || !consentChecked}
          >
            <Mail className="h-4 w-4" />
            Connect{' '}
            {selectedProvider === 'gmail'
              ? 'Gmail'
              : selectedProvider === 'outlook'
                ? 'Outlook'
                : 'Email'}
          </Button>
        </div>
      </div>
    </Card>
  )
}
