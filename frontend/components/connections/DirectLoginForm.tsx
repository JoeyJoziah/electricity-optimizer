'use client'

import React, { useState, useEffect } from 'react'
import { cn } from '@/lib/utils/cn'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/input'
import { KeyRound, ExternalLink, AlertCircle, CheckCircle2 } from 'lucide-react'

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

export function DirectLoginForm({ onComplete }: DirectLoginFormProps) {
  const [suppliers, setSuppliers] = useState<RegistrySupplier[]>([])
  const [loadingSuppliers, setLoadingSuppliers] = useState(true)
  const [selectedSupplierId, setSelectedSupplierId] = useState('')
  const [consentChecked, setConsentChecked] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

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
        setSuccess(true)
        setTimeout(() => onComplete(), 1500)
      } else {
        const data = await res.json().catch(() => null)
        setError(data?.detail || 'Failed to initiate connection. Please try again.')
      }
    } catch {
      setError('Network error. Please check your connection and try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (success) {
    return (
      <Card className="p-8 text-center">
        <CheckCircle2 className="mx-auto h-12 w-12 text-success-500" />
        <h3 className="mt-4 text-lg font-semibold text-gray-900">
          Connection Initiated
        </h3>
        <p className="mt-2 text-sm text-gray-500">
          We are setting up your utility account connection. This may take a few moments.
        </p>
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
            Link your provider account to automatically sync rates and billing data
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
                your utility account data. We never store your login credentials.
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
