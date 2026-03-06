import React from 'react'
import { Loader2 } from 'lucide-react'
import type { ParseResult } from './BillUploadTypes'

interface BillUploadProgressBarProps {
  uploading: boolean
  uploadProgress: number
}

export function BillUploadProgressBar({
  uploading,
  uploadProgress,
}: BillUploadProgressBarProps) {
  if (!uploading && !(uploadProgress > 0 && uploadProgress < 100)) {
    return null
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-gray-500">
        <span>Uploading...</span>
        <span>{uploadProgress}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200">
        <div
          className="h-full rounded-full bg-primary-500 transition-all duration-300 ease-out"
          style={{ width: `${uploadProgress}%` }}
          role="progressbar"
          aria-valuenow={uploadProgress}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Upload progress"
        />
      </div>
    </div>
  )
}

interface BillUploadProcessingStatusProps {
  parseResult: ParseResult
  pollCount: number
}

export function BillUploadProcessingStatus({
  parseResult,
  pollCount,
}: BillUploadProcessingStatusProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-primary-200 bg-primary-50 p-8">
      <Loader2 className="h-8 w-8 animate-spin text-primary-500" />
      <p className="mt-4 text-sm font-medium text-primary-700">
        {parseResult.status === 'pending'
          ? 'Queued for processing...'
          : 'Analyzing your bill...'}
      </p>
      <p className="mt-1 text-xs text-primary-500">
        This usually takes 10-30 seconds
      </p>
      {pollCount > 10 && (
        <p className="mt-2 text-xs text-primary-400">
          Still working on it...
        </p>
      )}
    </div>
  )
}
