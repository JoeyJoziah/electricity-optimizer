import React from 'react'
import { Button } from '@/components/ui/button'
import {
  CheckCircle2,
  AlertCircle,
  RotateCcw,
  Zap,
  Calendar,
  DollarSign,
  Gauge,
  File,
} from 'lucide-react'
import { ExtractedField } from './ExtractedField'
import { formatDate, formatCurrency } from './BillUploadTypes'
import type { ExtractedData } from './BillUploadTypes'

interface BillUploadSuccessProps {
  extractedData: ExtractedData
  onComplete: () => void
  onClearFile: () => void
}

export function BillUploadSuccess({
  extractedData,
  onComplete,
  onClearFile,
}: BillUploadSuccessProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 rounded-lg border border-success-200 bg-success-50 p-3">
        <CheckCircle2 className="h-5 w-5 text-success-500 shrink-0" />
        <p className="text-sm font-medium text-success-700">
          Bill processed successfully
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {extractedData.rate_per_kwh !== null && (
          <ExtractedField
            icon={Zap}
            label="Rate"
            value={`${(extractedData.rate_per_kwh * 100).toFixed(2)} c/kWh`}
            highlight
          />
        )}
        {extractedData.supplier_name && (
          <ExtractedField
            icon={File}
            label="Supplier"
            value={extractedData.supplier_name}
          />
        )}
        {extractedData.period_start &&
          extractedData.period_end && (
            <ExtractedField
              icon={Calendar}
              label="Period"
              value={`${formatDate(extractedData.period_start)} - ${formatDate(extractedData.period_end)}`}
            />
          )}
        {extractedData.usage_kwh !== null && (
          <ExtractedField
            icon={Gauge}
            label="Usage"
            value={`${extractedData.usage_kwh.toLocaleString()} kWh`}
          />
        )}
        {extractedData.amount !== null && (
          <ExtractedField
            icon={DollarSign}
            label="Amount"
            value={formatCurrency(
              extractedData.amount,
              extractedData.currency
            )}
          />
        )}
      </div>

      <div className="flex items-center gap-3 pt-2">
        <Button
          variant="primary"
          className="flex-1"
          onClick={onComplete}
        >
          <CheckCircle2 className="h-4 w-4" />
          Done
        </Button>
        <Button
          variant="outline"
          onClick={onClearFile}
        >
          Upload Another
        </Button>
      </div>
    </div>
  )
}

interface BillUploadFailureProps {
  errorMessage: string | null
  onRetry: () => void
  onClearFile: () => void
}

export function BillUploadFailure({
  errorMessage,
  onRetry,
  onClearFile,
}: BillUploadFailureProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2 rounded-lg border border-danger-200 bg-danger-50 p-4">
        <AlertCircle className="mt-0.5 h-5 w-5 text-danger-500 shrink-0" />
        <div>
          <p className="text-sm font-medium text-danger-700">
            Failed to process bill
          </p>
          <p className="mt-1 text-sm text-danger-600">
            {errorMessage ||
              'We could not extract data from this file. Please ensure it is a clear utility bill.'}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <Button variant="primary" onClick={onRetry}>
          <RotateCcw className="h-4 w-4" />
          Retry Upload
        </Button>
        <Button
          variant="outline"
          onClick={onClearFile}
        >
          Choose Different File
        </Button>
      </div>
    </div>
  )
}
