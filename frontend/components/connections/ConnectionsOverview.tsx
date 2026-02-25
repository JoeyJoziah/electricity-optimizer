'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { ConnectionMethodPicker } from './ConnectionMethodPicker'
import { ConnectionCard } from './ConnectionCard'
import { DirectLoginForm } from './DirectLoginForm'
import { EmailConnectionFlow } from './EmailConnectionFlow'
import { ConnectionUploadFlow } from './ConnectionUploadFlow'
import { ConnectionRates } from './ConnectionRates'
import { Link2, ArrowLeft, Loader2 } from 'lucide-react'

type View =
  | 'overview'
  | 'adding-direct'
  | 'adding-email'
  | 'adding-upload'
  | 'viewing-rates'

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
          className="mb-6 flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 transition-colors"
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
    <div className="space-y-8">
      {/* Loading state */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
          <span className="ml-2 text-sm text-gray-500">
            Loading connections...
          </span>
        </div>
      )}

      {/* Error state */}
      {error && error !== 'upgrade' && (
        <div className="rounded-xl border border-danger-200 bg-danger-50 p-4 text-center">
          <p className="text-sm text-danger-700">{error}</p>
          <button
            onClick={fetchConnections}
            className="mt-2 text-sm font-medium text-danger-600 hover:text-danger-800 transition-colors"
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
          <div className="space-y-3">
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
  )
}

function PaidFeatureGate() {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-8 text-center">
      <Link2 className="mx-auto h-12 w-12 text-gray-300" />
      <h3 className="mt-4 text-lg font-semibold text-gray-900">
        Upgrade to Connect
      </h3>
      <p className="mt-2 text-sm text-gray-500">
        Utility connections are available on Pro and Business plans. Sync your
        rates automatically.
      </p>
      <a
        href="/pricing"
        className="mt-6 inline-block rounded-lg bg-primary-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-primary-700 transition-colors"
      >
        View Plans
      </a>
    </div>
  )
}
