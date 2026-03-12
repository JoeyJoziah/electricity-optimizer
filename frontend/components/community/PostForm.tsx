'use client'

import React from 'react'
import { useCreatePost } from '@/lib/hooks/useCommunity'
import { useSettingsStore } from '@/lib/store/settings'
import { useAuth } from '@/lib/hooks/useAuth'

const POST_TYPES = [
  { value: 'tip', label: 'Tip' },
  { value: 'rate_report', label: 'Rate Report' },
  { value: 'discussion', label: 'Discussion' },
  { value: 'review', label: 'Review' },
]

const UTILITY_TYPES = [
  { value: 'electricity', label: 'Electricity' },
  { value: 'natural_gas', label: 'Natural Gas' },
  { value: 'heating_oil', label: 'Heating Oil' },
  { value: 'propane', label: 'Propane' },
  { value: 'community_solar', label: 'Community Solar' },
  { value: 'water', label: 'Water' },
  { value: 'general', label: 'General' },
]

const RATE_UNITS = ['kWh', 'therm', 'gallon', 'CCF']

interface PostFormProps {
  defaultUtilityType?: string
  onSuccess?: () => void
}

export function PostForm({ defaultUtilityType, onSuccess }: PostFormProps) {
  const { user } = useAuth()
  const region = useSettingsStore((s) => s.region)
  const mutation = useCreatePost()

  const [expanded, setExpanded] = React.useState(false)
  const [title, setTitle] = React.useState('')
  const [body, setBody] = React.useState('')
  const [postType, setPostType] = React.useState('tip')
  const [utilityType, setUtilityType] = React.useState(defaultUtilityType || 'electricity')
  const [ratePerUnit, setRatePerUnit] = React.useState('')
  const [rateUnit, setRateUnit] = React.useState('kWh')
  const [supplierName, setSupplierName] = React.useState('')
  const [errors, setErrors] = React.useState<Record<string, string>>({})

  if (!user) {
    return (
      <div data-testid="post-form-auth-required" className="rounded-xl border bg-gray-50 p-4 text-center">
        <p className="text-sm text-gray-500">
          <a href="/auth/login" className="font-medium text-primary-600 hover:underline">Sign in</a>
          {' '}to share with the community.
        </p>
      </div>
    )
  }

  if (!expanded) {
    return (
      <button
        onClick={() => setExpanded(true)}
        data-testid="post-form-expand"
        className="w-full rounded-xl border border-dashed border-gray-300 bg-white p-4 text-sm text-gray-500 hover:border-primary-400 hover:text-primary-600 transition-colors"
      >
        Share a tip, rate report, or discussion...
      </button>
    )
  }

  function validate(): boolean {
    const errs: Record<string, string> = {}
    if (!title || title.length < 3) errs.title = 'Title must be at least 3 characters'
    if (title.length > 200) errs.title = 'Title must be under 200 characters'
    if (!body || body.length < 10) errs.body = 'Body must be at least 10 characters'
    if (body.length > 5000) errs.body = 'Body must be under 5000 characters'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!validate()) return

    mutation.mutate(
      {
        title,
        body,
        post_type: postType,
        utility_type: utilityType,
        region: region || 'us_ct',
        rate_per_unit: postType === 'rate_report' && ratePerUnit ? parseFloat(ratePerUnit) : null,
        rate_unit: postType === 'rate_report' ? rateUnit : null,
        supplier_name: supplierName || null,
      },
      {
        onSuccess: () => {
          setTitle('')
          setBody('')
          setRatePerUnit('')
          setSupplierName('')
          setExpanded(false)
          onSuccess?.()
        },
      },
    )
  }

  return (
    <form onSubmit={handleSubmit} data-testid="post-form" className="rounded-xl border bg-white p-4 space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Post Type</label>
          <select
            value={postType}
            onChange={(e) => setPostType(e.target.value)}
            className="w-full rounded-lg border px-3 py-2 text-sm"
            data-testid="post-type-select"
          >
            {POST_TYPES.map((pt) => (
              <option key={pt.value} value={pt.value}>{pt.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Utility Type</label>
          <select
            value={utilityType}
            onChange={(e) => setUtilityType(e.target.value)}
            className="w-full rounded-lg border px-3 py-2 text-sm"
            data-testid="utility-type-select"
          >
            {UTILITY_TYPES.map((ut) => (
              <option key={ut.value} value={ut.value}>{ut.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">Title</label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Brief summary..."
          className="w-full rounded-lg border px-3 py-2 text-sm"
          data-testid="post-title-input"
        />
        {errors.title && <p className="mt-1 text-xs text-red-500" data-testid="title-error">{errors.title}</p>}
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">Body</label>
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Share details..."
          rows={4}
          className="w-full rounded-lg border px-3 py-2 text-sm"
          data-testid="post-body-input"
        />
        {errors.body && <p className="mt-1 text-xs text-red-500" data-testid="body-error">{errors.body}</p>}
      </div>

      {/* Rate fields — only for rate_report */}
      {postType === 'rate_report' && (
        <div className="grid gap-4 sm:grid-cols-3" data-testid="rate-fields">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Rate per unit</label>
            <input
              type="number"
              step="0.0001"
              value={ratePerUnit}
              onChange={(e) => setRatePerUnit(e.target.value)}
              placeholder="0.1850"
              className="w-full rounded-lg border px-3 py-2 text-sm"
              data-testid="rate-input"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Unit</label>
            <select
              value={rateUnit}
              onChange={(e) => setRateUnit(e.target.value)}
              className="w-full rounded-lg border px-3 py-2 text-sm"
              data-testid="rate-unit-select"
            >
              {RATE_UNITS.map((u) => (
                <option key={u} value={u}>{u}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Supplier (optional)</label>
            <input
              type="text"
              value={supplierName}
              onChange={(e) => setSupplierName(e.target.value)}
              placeholder="Supplier name"
              className="w-full rounded-lg border px-3 py-2 text-sm"
              data-testid="supplier-input"
            />
          </div>
        </div>
      )}

      {/* Consent */}
      <p className="text-xs text-gray-400" data-testid="consent-text">
        Your post will be visible to other users in your state. We review content for safety.
      </p>

      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={mutation.isPending}
          className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50 transition-colors"
          data-testid="post-submit-btn"
        >
          {mutation.isPending ? 'Posting...' : 'Post'}
        </button>
        <button
          type="button"
          onClick={() => setExpanded(false)}
          className="text-sm text-gray-500 hover:text-gray-700"
        >
          Cancel
        </button>
        {mutation.isError && (
          <span className="text-xs text-red-500" data-testid="post-submit-error">
            Failed to create post. Try again.
          </span>
        )}
      </div>
    </form>
  )
}
