'use client'

import React, { useState } from 'react'
import { useCommunitySolarSavings } from '@/lib/hooks/useCommunitySolar'
import { Calculator, DollarSign } from 'lucide-react'

/**
 * CommunitySolarService — Savings calculator component.
 * Named this way to match the export in CommunitySolarContent.
 */
export function CommunitySolarService() {
  const [bill, setBill] = useState('')
  const [percent, setPercent] = useState('')
  const [submitted, setSubmitted] = useState(false)

  const { data: savings, isLoading } = useCommunitySolarSavings(
    submitted && bill ? bill : null,
    submitted && percent ? percent : null
  )

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (bill && percent) {
      setSubmitted(true)
    }
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5">
      <div className="flex items-center gap-2 mb-4">
        <Calculator className="h-5 w-5 text-primary-600" />
        <h2 className="text-lg font-semibold text-gray-900">
          Savings Calculator
        </h2>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3">
        <div>
          <label
            htmlFor="monthly-bill"
            className="block text-xs font-medium text-gray-700 mb-1"
          >
            Monthly Bill ($)
          </label>
          <input
            id="monthly-bill"
            type="number"
            min="1"
            step="0.01"
            value={bill}
            onChange={(e) => {
              setBill(e.target.value)
              setSubmitted(false)
            }}
            placeholder="150"
            className="w-32 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
          />
        </div>
        <div>
          <label
            htmlFor="savings-percent"
            className="block text-xs font-medium text-gray-700 mb-1"
          >
            Savings (%)
          </label>
          <input
            id="savings-percent"
            type="number"
            min="1"
            max="100"
            step="0.1"
            value={percent}
            onChange={(e) => {
              setPercent(e.target.value)
              setSubmitted(false)
            }}
            placeholder="10"
            className="w-24 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
          />
        </div>
        <button
          type="submit"
          disabled={!bill || !percent}
          className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Calculate
        </button>
      </form>

      {isLoading && (
        <div className="mt-4 animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-1/2" />
        </div>
      )}

      {savings && !isLoading && (
        <div className="mt-4 grid grid-cols-3 gap-4">
          <div className="rounded-lg bg-success-50 p-3 text-center">
            <DollarSign className="mx-auto h-5 w-5 text-success-600 mb-1" />
            <p className="text-lg font-bold text-success-700">
              ${savings.monthly_savings}
            </p>
            <p className="text-xs text-success-600">Monthly Savings</p>
          </div>
          <div className="rounded-lg bg-success-50 p-3 text-center">
            <p className="text-lg font-bold text-success-700">
              ${savings.annual_savings}
            </p>
            <p className="text-xs text-success-600">Annual Savings</p>
          </div>
          <div className="rounded-lg bg-success-50 p-3 text-center">
            <p className="text-lg font-bold text-success-700">
              ${savings.five_year_savings}
            </p>
            <p className="text-xs text-success-600">5-Year Savings</p>
          </div>
        </div>
      )}
    </div>
  )
}
