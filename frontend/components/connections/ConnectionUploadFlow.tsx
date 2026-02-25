'use client'

import React, { useState, useCallback } from 'react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { BillUploadForm } from './BillUploadForm'
import { ConnectionRates } from './ConnectionRates'
import {
  Upload,
  Loader2,
  AlertCircle,
  CheckCircle2,
  ArrowLeft,
} from 'lucide-react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface ConnectionUploadFlowProps {
  onComplete: () => void
}

type FlowStep = 'creating' | 'uploading' | 'results'

interface CreatedConnection {
  id: string
  supplier_name: string | null
}

export function ConnectionUploadFlow({ onComplete }: ConnectionUploadFlowProps) {
  const [step, setStep] = useState<FlowStep>('creating')
  const [connection, setConnection] = useState<CreatedConnection | null>(null)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const createUploadConnection = useCallback(async () => {
    try {
      setCreating(true)
      setError(null)

      const res = await fetch(`${API_BASE}/api/v1/connections/upload`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          method: 'manual_upload',
        }),
      })

      if (res.ok) {
        const data = await res.json()
        setConnection({
          id: data.id || data.connection_id,
          supplier_name: data.supplier_name || null,
        })
        setStep('uploading')
      } else if (res.status === 403) {
        setError('upgrade')
      } else {
        const data = await res.json().catch(() => null)
        setError(data?.detail || 'Failed to create upload connection. Please try again.')
      }
    } catch {
      setError('Network error. Please check your connection and try again.')
    } finally {
      setCreating(false)
    }
  }, [])

  // Auto-create connection on mount
  React.useEffect(() => {
    createUploadConnection()
  }, [createUploadConnection])

  if (error === 'upgrade') {
    return (
      <Card padding="lg" className="text-center">
        <Upload className="mx-auto h-12 w-12 text-gray-300" />
        <h3 className="mt-4 text-lg font-semibold text-gray-900">
          Upgrade Required
        </h3>
        <p className="mt-2 text-sm text-gray-500">
          Bill upload is available on Pro and Business plans.
        </p>
        <a
          href="/pricing"
          className="mt-6 inline-block rounded-lg bg-primary-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-primary-700 transition-colors"
        >
          View Plans
        </a>
      </Card>
    )
  }

  // Step 1: Creating the connection
  if (step === 'creating') {
    return (
      <Card padding="lg">
        {creating ? (
          <div className="flex flex-col items-center justify-center py-8">
            <Loader2 className="h-8 w-8 animate-spin text-primary-500" />
            <p className="mt-4 text-sm text-gray-500">
              Setting up bill upload...
            </p>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-8">
            <AlertCircle className="h-8 w-8 text-danger-500" />
            <p className="mt-4 text-sm text-danger-700">{error}</p>
            <div className="mt-4 flex items-center gap-3">
              <Button variant="primary" onClick={createUploadConnection}>
                Try Again
              </Button>
              <Button variant="outline" onClick={onComplete}>
                Back to Connections
              </Button>
            </div>
          </div>
        ) : null}
      </Card>
    )
  }

  // Step 2: Upload the bill
  if (step === 'uploading' && connection) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <StepIndicator current={2} total={3} />
          <p className="text-sm text-gray-500">Upload your utility bill</p>
        </div>
        <BillUploadForm
          connectionId={connection.id}
          onUploadComplete={() => setStep('results')}
          onComplete={onComplete}
        />
      </div>
    )
  }

  // Step 3: Show extracted rates
  if (step === 'results' && connection) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <StepIndicator current={3} total={3} />
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-success-500" />
            <p className="text-sm text-gray-700">Bill processed successfully</p>
          </div>
        </div>
        <ConnectionRates
          connectionId={connection.id}
          connectionMethod="bill_upload"
          supplierName={connection.supplier_name}
          onBack={onComplete}
          onUploadAnother={() => setStep('uploading')}
        />
      </div>
    )
  }

  return null
}

function StepIndicator({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center gap-1.5">
      {Array.from({ length: total }, (_, i) => {
        const stepNum = i + 1
        const isActive = stepNum === current
        const isComplete = stepNum < current

        return (
          <div
            key={stepNum}
            className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium ${
              isActive
                ? 'bg-primary-600 text-white'
                : isComplete
                  ? 'bg-success-100 text-success-700'
                  : 'bg-gray-100 text-gray-400'
            }`}
          >
            {isComplete ? (
              <CheckCircle2 className="h-3.5 w-3.5" />
            ) : (
              stepNum
            )}
          </div>
        )
      })}
    </div>
  )
}
