'use client'

import React, { useState } from 'react'
import { cn } from '@/lib/utils/cn'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Mail, AlertCircle, Clock } from 'lucide-react'

interface EmailConnectionFlowProps {
  onComplete: () => void
}

type EmailProvider = 'gmail' | 'outlook'

export function EmailConnectionFlow({ onComplete }: EmailConnectionFlowProps) {
  const [selectedProvider, setSelectedProvider] = useState<EmailProvider | null>(
    null
  )
  const [consentChecked, setConsentChecked] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showComingSoon, setShowComingSoon] = useState(false)

  const handleConnect = () => {
    if (!selectedProvider) {
      setError('Please select an email provider')
      return
    }
    if (!consentChecked) {
      setError('You must consent to email scanning before connecting')
      return
    }

    // Phase 1: Show "Coming Soon" — real OAuth will be wired in Phase 3
    setShowComingSoon(true)
  }

  if (showComingSoon) {
    return (
      <Card className="p-8 text-center">
        <Clock className="mx-auto h-12 w-12 text-primary-400" />
        <h3 className="mt-4 text-lg font-semibold text-gray-900">
          Coming Soon
        </h3>
        <p className="mt-2 text-sm text-gray-500">
          Email inbox scanning is launching in the next release. We will notify
          you when it is available.
        </p>
        <Button
          variant="outline"
          className="mt-6"
          onClick={onComplete}
        >
          Back to Connections
        </Button>
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
          <Badge variant="info">Phase 3</Badge>
        </div>
      </div>
    </Card>
  )
}
