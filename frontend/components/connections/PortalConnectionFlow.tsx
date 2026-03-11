'use client'

import React, { useState, useEffect } from 'react'
import { Globe, ArrowLeft, Loader2, CheckCircle, AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input, Checkbox } from '@/components/ui/input'
import { API_ORIGIN } from '@/lib/config/env'
import {
  createPortalConnection,
  triggerPortalScrape,
  type PortalScrapeResponse,
} from '@/lib/api/portal'

interface PortalConnectionFlowProps {
  onBack: () => void
  onSuccess: () => void
}

interface RegistrySupplier {
  id: string
  name: string
  region: string
  utility_type: string
}

type FlowStep = 'form' | 'submitting' | 'scraping' | 'success' | 'error'

export function PortalConnectionFlow({ onBack, onSuccess }: PortalConnectionFlowProps) {
  const [suppliers, setSuppliers] = useState<RegistrySupplier[]>([])
  const [loadingSuppliers, setLoadingSuppliers] = useState(true)

  // Form fields
  const [selectedSupplierId, setSelectedSupplierId] = useState('')
  const [portalUsername, setPortalUsername] = useState('')
  const [portalPassword, setPortalPassword] = useState('')
  const [portalLoginUrl, setPortalLoginUrl] = useState('')
  const [consentChecked, setConsentChecked] = useState(false)

  // Validation
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  // Flow state
  const [step, setStep] = useState<FlowStep>('form')
  const [error, setError] = useState<string | null>(null)
  const [scrapeResult, setScrapeResult] = useState<PortalScrapeResponse | null>(null)

  // Load suppliers on mount
  useEffect(() => {
    async function loadSuppliers() {
      try {
        const res = await fetch(`${API_ORIGIN}/api/v1/suppliers/registry`, {
          credentials: 'include',
        })
        if (res.ok) {
          const data = await res.json()
          setSuppliers(data.suppliers || data || [])
        }
      } catch {
        // Supplier registry unavailable - form still renders
      } finally {
        setLoadingSuppliers(false)
      }
    }
    loadSuppliers()
  }, [])

  function validate(): boolean {
    const errors: Record<string, string> = {}

    if (!selectedSupplierId) {
      errors.supplier = 'Please select a utility provider'
    }
    if (!portalUsername.trim()) {
      errors.username = 'Username is required'
    }
    if (!portalPassword) {
      errors.password = 'Password is required'
    }
    if (!consentChecked) {
      errors.consent = 'You must consent before connecting'
    }

    setFieldErrors(errors)
    return Object.keys(errors).length === 0
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    if (!validate()) return

    try {
      setStep('submitting')

      const connection = await createPortalConnection({
        supplier_id: selectedSupplierId,
        portal_username: portalUsername.trim(),
        portal_password: portalPassword,
        portal_login_url: portalLoginUrl.trim() || undefined,
        consent_given: true,
      })

      // Automatically trigger a scrape after connection creation
      try {
        setStep('scraping')
        const result = await triggerPortalScrape(connection.connection_id)
        setScrapeResult(result)
        setStep('success')
      } catch {
        // Scrape failed but connection was created successfully
        setScrapeResult({
          connection_id: connection.connection_id,
          status: 'pending',
          rates_extracted: 0,
          error: 'Scrape will be retried automatically',
          scraped_at: null,
        })
        setStep('success')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create portal connection')
      setStep('error')
    }
  }

  // Clear field error when user interacts
  function clearFieldError(field: string) {
    setFieldErrors((prev) => {
      const next = { ...prev }
      delete next[field]
      return next
    })
  }

  const isFormValid =
    selectedSupplierId && portalUsername.trim() && portalPassword && consentChecked

  // Success state
  if (step === 'success') {
    return (
      <Card padding="lg">
        <div className="flex items-center gap-3 mb-6">
          <CheckCircle className="h-6 w-6 text-success-500" />
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              Portal Connection Created
            </h2>
            <p className="text-sm text-gray-500">
              Your utility portal account has been linked successfully.
            </p>
          </div>
        </div>

        {scrapeResult && (
          <div
            className={cn(
              'rounded-lg border p-4 mb-6',
              scrapeResult.rates_extracted > 0
                ? 'border-success-200 bg-success-50'
                : 'border-gray-200 bg-gray-50'
            )}
          >
            {scrapeResult.rates_extracted > 0 ? (
              <p className="text-sm text-success-700">
                Successfully extracted{' '}
                <span className="font-semibold">{scrapeResult.rates_extracted}</span>{' '}
                rate{scrapeResult.rates_extracted !== 1 ? 's' : ''} from your utility
                portal.
              </p>
            ) : (
              <p className="text-sm text-gray-600">
                {scrapeResult.error ||
                  'No rates extracted yet. The scrape will be retried automatically.'}
              </p>
            )}
          </div>
        )}

        <Button variant="primary" className="w-full" onClick={onSuccess}>
          Done
        </Button>
      </Card>
    )
  }

  // Error state (connection creation failed)
  if (step === 'error') {
    return (
      <Card padding="lg">
        <div className="flex items-center gap-3 mb-6">
          <AlertCircle className="h-6 w-6 text-danger-500" />
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              Connection Failed
            </h2>
            <p className="text-sm text-danger-600">
              {error || 'An unexpected error occurred'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="primary"
            className="flex-1"
            onClick={() => {
              setStep('form')
              setError(null)
            }}
          >
            Try Again
          </Button>
          <Button variant="outline" onClick={onBack}>
            Cancel
          </Button>
        </div>
      </Card>
    )
  }

  // Loading / scraping state
  if (step === 'submitting' || step === 'scraping') {
    return (
      <Card padding="lg">
        <div className="flex flex-col items-center justify-center py-12" role="status">
          <Loader2 className="h-8 w-8 animate-spin text-primary-500 mb-4" />
          <p className="text-sm font-medium text-gray-700">
            {step === 'submitting'
              ? 'Creating portal connection...'
              : 'Scraping your utility portal for rates...'}
          </p>
          <p className="mt-1 text-xs text-gray-500">
            This may take a moment
          </p>
        </div>
      </Card>
    )
  }

  // Form state
  return (
    <Card padding="lg">
      <div className="flex items-center gap-3 mb-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-100">
          <Globe className="h-5 w-5 text-purple-600" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            Connect Utility Portal
          </h2>
          <p className="text-sm text-gray-500">
            Log in to your utility provider website to import billing data
            automatically
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Supplier selector */}
        <div>
          <label
            htmlFor="portal-supplier-select"
            className="mb-1.5 block text-sm font-medium text-gray-700"
          >
            Utility Provider
          </label>
          {loadingSuppliers ? (
            <div className="h-10 w-full animate-pulse rounded-lg bg-gray-100" />
          ) : (
            <select
              id="portal-supplier-select"
              value={selectedSupplierId}
              onChange={(e) => {
                setSelectedSupplierId(e.target.value)
                clearFieldError('supplier')
              }}
              className={cn(
                'block w-full rounded-lg border bg-white px-3 py-2.5',
                'text-gray-900 focus:outline-none focus:ring-2 focus:ring-offset-0',
                'transition-all duration-200',
                'hover:border-gray-400',
                'disabled:cursor-not-allowed disabled:bg-gray-50',
                fieldErrors.supplier
                  ? 'border-danger-300 focus:border-danger-500 focus:ring-danger-500'
                  : 'border-gray-300 focus:border-primary-500 focus:ring-primary-500'
              )}
              aria-invalid={fieldErrors.supplier ? 'true' : undefined}
              aria-describedby={
                fieldErrors.supplier ? 'portal-supplier-error' : undefined
              }
            >
              <option value="">Select your utility provider...</option>
              {suppliers.map((supplier) => (
                <option key={supplier.id} value={supplier.id}>
                  {supplier.name}
                </option>
              ))}
            </select>
          )}
          {fieldErrors.supplier && (
            <p
              id="portal-supplier-error"
              className="mt-1.5 text-sm text-danger-600"
              role="alert"
            >
              {fieldErrors.supplier}
            </p>
          )}
        </div>

        {/* Username */}
        <Input
          label="Portal Username"
          id="portal-username"
          type="text"
          placeholder="Your utility portal username or email"
          value={portalUsername}
          onChange={(e) => {
            setPortalUsername(e.target.value)
            clearFieldError('username')
          }}
          error={fieldErrors.username}
          autoComplete="username"
        />

        {/* Password */}
        <Input
          label="Portal Password"
          id="portal-password"
          type="password"
          placeholder="Your utility portal password"
          value={portalPassword}
          onChange={(e) => {
            setPortalPassword(e.target.value)
            clearFieldError('password')
          }}
          error={fieldErrors.password}
          autoComplete="current-password"
        />

        {/* Optional login URL */}
        <Input
          label="Portal Login URL"
          labelSuffix="(optional)"
          id="portal-login-url"
          type="url"
          placeholder="https://myutility.com/login"
          value={portalLoginUrl}
          onChange={(e) => setPortalLoginUrl(e.target.value)}
          helperText="Override the default login page if your utility uses a custom URL"
        />

        {/* Security notice */}
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
          <div className="flex items-start gap-3">
            <Globe className="mt-0.5 h-4 w-4 text-gray-400 shrink-0" />
            <div>
              <p className="text-sm font-medium text-gray-700">
                Secure Portal Access
              </p>
              <p className="mt-1 text-xs text-gray-500">
                Your credentials are encrypted and used only to access your
                utility portal for rate data extraction. We use AES-256
                encryption at rest.
              </p>
            </div>
          </div>
        </div>

        {/* Consent */}
        <div>
          <Checkbox
            label="I consent to RateShift securely storing my portal credentials and accessing my utility billing data for rate comparison and optimization"
            checked={consentChecked}
            onChange={(e) => {
              setConsentChecked(e.target.checked)
              clearFieldError('consent')
            }}
          />
          {fieldErrors.consent && (
            <p className="mt-1.5 text-sm text-danger-600" role="alert">
              {fieldErrors.consent}
            </p>
          )}
        </div>

        {/* Submit */}
        <Button
          type="submit"
          variant="primary"
          className="w-full"
          disabled={!isFormValid}
        >
          <Globe className="h-4 w-4" />
          Connect Utility Portal
        </Button>
      </form>
    </Card>
  )
}
