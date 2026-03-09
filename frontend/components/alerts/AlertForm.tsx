'use client'

import React, { useState } from 'react'
import Link from 'next/link'
import { Input, Checkbox } from '@/components/ui/input'
import { useCreateAlert } from '@/lib/hooks/useAlerts'
import { ApiClientError } from '@/lib/api/client'
import { US_REGIONS } from '@/lib/constants/regions'

interface AlertFormProps {
  onSuccess?: () => void
}

export function AlertForm({ onSuccess }: AlertFormProps) {
  const createMutation = useCreateAlert()

  const [region, setRegion] = useState('')
  const [priceBelow, setPriceBelow] = useState('')
  const [priceAbove, setPriceAbove] = useState('')
  const [notifyOptimalWindows, setNotifyOptimalWindows] = useState(true)
  const [validationError, setValidationError] = useState('')

  const isTierLimitError =
    createMutation.isError &&
    createMutation.error instanceof ApiClientError &&
    createMutation.error.status === 403

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setValidationError('')

    if (!region) {
      setValidationError('Please select a region.')
      return
    }

    const below = priceBelow ? parseFloat(priceBelow) : null
    const above = priceAbove ? parseFloat(priceAbove) : null

    if (below === null && above === null && !notifyOptimalWindows) {
      setValidationError(
        'At least one condition is required: price below, price above, or optimal window notifications.'
      )
      return
    }

    if (below !== null && (isNaN(below) || below <= 0)) {
      setValidationError('Price below must be a positive number.')
      return
    }

    if (above !== null && (isNaN(above) || above <= 0)) {
      setValidationError('Price above must be a positive number.')
      return
    }

    createMutation.mutate(
      {
        region,
        price_below: below,
        price_above: above,
        notify_optimal_windows: notifyOptimalWindows,
      },
      {
        onSuccess: () => {
          // Reset form
          setRegion('')
          setPriceBelow('')
          setPriceAbove('')
          setNotifyOptimalWindows(true)
          onSuccess?.()
        },
      }
    )
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4" data-testid="alert-form">
      <h3 className="text-base font-medium text-gray-900">Create New Alert</h3>

      {/* Region selector */}
      <div className="w-full">
        <label htmlFor="alert-region" className="mb-1.5 block text-sm font-medium text-gray-700">
          Region
        </label>
        <select
          id="alert-region"
          value={region}
          onChange={(e) => setRegion(e.target.value)}
          className="block w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-gray-900 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500 transition-all duration-200 hover:border-gray-400"
          data-testid="region-select"
        >
          <option value="">Select a region...</option>
          {US_REGIONS.map((group) => (
            <optgroup key={group.label} label={group.label}>
              {group.states.map((state) => (
                <option key={state.value} value={state.value}>
                  {state.label} ({state.abbr})
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </div>

      {/* Price thresholds */}
      <div className="grid gap-4 sm:grid-cols-2">
        <Input
          label="Price Below"
          labelSuffix="($/kWh)"
          type="number"
          step="0.0001"
          min="0.0001"
          placeholder="e.g. 0.20"
          value={priceBelow}
          onChange={(e) => setPriceBelow(e.target.value)}
          helperText="Alert when price drops to or below this value"
        />
        <Input
          label="Price Above"
          labelSuffix="($/kWh)"
          type="number"
          step="0.0001"
          min="0.0001"
          placeholder="e.g. 0.30"
          value={priceAbove}
          onChange={(e) => setPriceAbove(e.target.value)}
          helperText="Alert when price rises to or above this value"
        />
      </div>

      {/* Optimal windows checkbox */}
      <Checkbox
        label="Notify me about optimal usage windows"
        checked={notifyOptimalWindows}
        onChange={(e) => setNotifyOptimalWindows(e.target.checked)}
      />

      {/* Validation error */}
      {validationError && (
        <p className="text-sm text-danger-600" role="alert" data-testid="form-error">
          {validationError}
        </p>
      )}

      {/* Tier limit error (403) — styled as an upgrade prompt */}
      {isTierLimitError && (
        <div
          className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-800"
          role="alert"
          data-testid="tier-limit-error"
        >
          Free plan is limited to 1 alert.{' '}
          <Link
            href="/pricing"
            className="font-medium text-amber-900 underline hover:no-underline"
          >
            Upgrade to Pro
          </Link>{' '}
          for unlimited alerts.
        </div>
      )}

      {/* Mutation error (non-403) */}
      {createMutation.isError && !isTierLimitError && (
        <p className="text-sm text-danger-600" role="alert">
          {createMutation.error?.message ?? 'Failed to create alert. Please try again.'}
        </p>
      )}

      {/* Submit */}
      <div className="flex justify-end">
        <button
          type="submit"
          disabled={createMutation.isPending}
          className="inline-flex items-center rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
          data-testid="submit-alert"
        >
          {createMutation.isPending ? 'Creating...' : 'Create Alert'}
        </button>
      </div>
    </form>
  )
}
