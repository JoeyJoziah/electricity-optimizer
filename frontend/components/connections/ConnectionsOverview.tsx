'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { ConnectionMethodPicker } from './ConnectionMethodPicker'
import { ConnectionCard } from './ConnectionCard'
import { DirectLoginForm } from './DirectLoginForm'
import { EmailConnectionFlow } from './EmailConnectionFlow'
import { ConnectionUploadFlow } from './ConnectionUploadFlow'
import { ConnectionRates } from './ConnectionRates'
import { ConnectionAnalytics } from './ConnectionAnalytics'
import { cn } from '@/lib/utils/cn'
import { Link2, ArrowLeft, Loader2 } from 'lucide-react'

type View =
  | 'overview'
  | 'adding-direct'
  | 'adding-email'
  | 'adding-upload'
  | 'viewing-rates'

type Tab = 'connections' | 'analytics'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface Connection {
  id: string
  method: string
  status: string
  supplier_name: string | null
  email_provider: string | null
  last_sync_at: string | null
  last_sync_error: string | null
  current_rate: number | null
  created_at: string
}

export function ConnectionsOverview() {
  const [view, setView] = useState<View>('overview')
  const [tab, setTab] = useState<Tab>('connections')
  const [connections, setConnections] = useState<Connection[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedConnectionId, setSelectedConnectionId] = useState<string | null>(null)

  const fetchConnections = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const res = await fetch(`${API_BASE}/api/v1/connections`, {
        credentials: 'include',
      })
      if (res.ok) {
        const data = await res.json()
        setConnections(data.connections || [])
      } else if (res.status === 403) {
        setError('upgrade')
      } else {
        setError('Failed to load connections')
      }
    } catch {
      setError('Failed to load connections')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchConnections()
  }, [fetchConnections])

  const handleViewRates = (connectionId: string) => {
    setSelectedConnectionId(connectionId)
    setView('viewing-rates')
  }

  const handleBackToOverview = () => {
    setView('overview')
    setSelectedConnectionId(null)
    fetchConnections()
  }

  if (error === 'upgrade') {
    return <PaidFeatureGate />
  }

  // Rate viewing
  if (view === 'viewing-rates' && selectedConnectionId) {
    const conn = connections.find((c) => c.id === selectedConnectionId)
    return (
      <ConnectionRates
        connectionId={selectedConnectionId}
        connectionMethod={conn?.method || 'unknown'}
        supplierName={conn?.supplier_name || null}
        onBack={handleBackToOverview}
        onUploadAnother={
          conn?.method === 'bill_upload' || conn?.method === 'manual_upload'
            ? () => {
                setView('adding-upload')
              }
            : undefined
        }
      />
    )
  }

  // Adding a connection
  if (
    view === 'adding-direct' ||
    view === 'adding-email' ||
    view === 'adding-upload'
  ) {
    return (
      <div>
        <button
          onClick={handleBackToOverview}
          className="mb-6 flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 rounded"
          aria-label="Back to connections overview"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to connections
        </button>
        {view === 'adding-direct' && (
          <DirectLoginForm onComplete={handleBackToOverview} />
        )}
        {view === 'adding-email' && (
          <EmailConnectionFlow onComplete={handleBackToOverview} />
        )}
        {view === 'adding-upload' && (
          <ConnectionUploadFlow onComplete={handleBackToOverview} />
        )}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Tab navigation */}
      <div className="flex border-b border-gray-200" role="tablist" aria-label="Connection views">
        <button
          role="tab"
          aria-selected={tab === 'connections'}
          aria-controls="panel-connections"
          id="tab-connections"
          onClick={() => setTab('connections')}
          className={cn(
            'px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 rounded-t',
            tab === 'connections'
              ? 'border-primary-600 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          )}
        >
          Connections
        </button>
        <button
          role="tab"
          aria-selected={tab === 'analytics'}
          aria-controls="panel-analytics"
          id="tab-analytics"
          onClick={() => setTab('analytics')}
          className={cn(
            'px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 rounded-t',
            tab === 'analytics'
              ? 'border-primary-600 text-primary-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          )}
        >
          Analytics
        </button>
      </div>

      {/* Connections tab panel */}
      {tab === 'connections' && (
        <div
          role="tabpanel"
          id="panel-connections"
          aria-labelledby="tab-connections"
          className="space-y-8"
        >
          {/* Loading state */}
          {loading && (
            <div className="flex items-center justify-center py-12" role="status">
              <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
              <span className="ml-2 text-sm text-gray-500">
                Loading connections...
              </span>
            </div>
          )}

          {/* Error state */}
          {error && error !== 'upgrade' && (
            <div className="rounded-xl border border-danger-200 bg-danger-50 p-4 text-center" role="alert">
              <p className="text-sm text-danger-700">{error}</p>
              <button
                onClick={fetchConnections}
                className="mt-2 text-sm font-medium text-danger-600 hover:text-danger-800 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger-500 focus-visible:ring-offset-2 rounded"
                aria-label="Retry loading connections"
              >
                Try again
              </button>
            </div>
          )}

          {/* Existing connections */}
          {!loading && connections.length > 0 && (
            <div>
              <h2 className="mb-4 text-lg font-semibold text-gray-900">
                Active Connections
              </h2>
              <div className="space-y-3" aria-live="polite">
                {connections.map((conn) => (
                  <ConnectionCard
                    key={conn.id}
                    connection={conn}
                    onDelete={fetchConnections}
                    onViewRates={handleViewRates}
                    onRefresh={fetchConnections}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Add new connection */}
          {!loading && (
            <div>
              <h2 className="mb-4 text-lg font-semibold text-gray-900">
                {connections.length > 0 ? 'Add Another Connection' : 'Get Started'}
              </h2>
              <ConnectionMethodPicker
                onSelectDirect={() => setView('adding-direct')}
                onSelectEmail={() => setView('adding-email')}
                onSelectUpload={() => setView('adding-upload')}
              />
            </div>
          )}
        </div>
      )}

      {/* Analytics tab panel */}
      {tab === 'analytics' && (
        <div
          role="tabpanel"
          id="panel-analytics"
          aria-labelledby="tab-analytics"
        >
          <ConnectionAnalytics />
        </div>
      )}
    </div>
  )
}

function PaidFeatureGate() {
  const features = [
    { label: 'Auto-sync utility rates', description: 'Connect directly to your utility for live rate updates' },
    { label: 'Email bill scanning', description: 'Forward bills and we extract rates automatically' },
    { label: 'Rate analytics & history', description: 'Track how your rates change over time' },
    { label: 'Savings recommendations', description: 'Personalized tips based on your actual usage' },
  ]

  return (
    <div className="space-y-8">
      {/* Main upgrade card */}
      <div className="rounded-xl border border-primary-200 bg-gradient-to-br from-primary-50 to-blue-50 p-8">
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-primary-100">
            <Link2 className="h-8 w-8 text-primary-600" aria-hidden="true" />
          </div>
          <h3 className="text-xl font-bold text-gray-900">
            Unlock Utility Connections
          </h3>
          <p className="mx-auto mt-2 max-w-md text-gray-600">
            Connect your utility account to get real-time rates, automated bill tracking,
            and personalized savings recommendations.
          </p>
        </div>

        {/* Feature list */}
        <div className="mx-auto mt-8 max-w-lg space-y-4">
          {features.map((feature) => (
            <div key={feature.label} className="flex items-start gap-3">
              <div className="mt-0.5 flex h-5 w-5 items-center justify-center rounded-full bg-primary-600">
                <svg className="h-3 w-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <div>
                <p className="font-medium text-gray-900">{feature.label}</p>
                <p className="text-sm text-gray-500">{feature.description}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Pricing */}
        <div className="mt-8 text-center">
          <p className="text-sm text-gray-500">Starting at</p>
          <p className="text-3xl font-bold text-gray-900">
            $4.99<span className="text-base font-normal text-gray-500">/mo</span>
          </p>
          <div className="mt-4 flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
            <a
              href="/pricing"
              className="inline-flex items-center justify-center rounded-lg bg-primary-600 px-8 py-3 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
            >
              View Plans & Pricing
            </a>
          </div>
        </div>
      </div>

      {/* What you can do now */}
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <h4 className="font-semibold text-gray-900">What you can do now (free)</h4>
        <ul className="mt-3 space-y-2">
          <li className="flex items-center gap-2 text-sm text-gray-600">
            <span className="h-1.5 w-1.5 rounded-full bg-success-500" />
            Compare suppliers in your state
          </li>
          <li className="flex items-center gap-2 text-sm text-gray-600">
            <span className="h-1.5 w-1.5 rounded-full bg-success-500" />
            View live electricity prices
          </li>
          <li className="flex items-center gap-2 text-sm text-gray-600">
            <span className="h-1.5 w-1.5 rounded-full bg-success-500" />
            Get price forecasts and optimal time recommendations
          </li>
        </ul>
        <div className="mt-4">
          <a
            href="/suppliers"
            className="text-sm font-medium text-primary-600 hover:text-primary-700 transition-colors"
          >
            Browse free supplier comparisons &rarr;
          </a>
        </div>
      </div>
    </div>
  )
}
