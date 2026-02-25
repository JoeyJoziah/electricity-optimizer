'use client'

import React, { useState, useRef, useCallback, useEffect } from 'react'
import { cn } from '@/lib/utils/cn'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Upload,
  FileText,
  X,
  AlertCircle,
  CheckCircle2,
  Loader2,
  RotateCcw,
  Image as ImageIcon,
  File,
  Zap,
  Calendar,
  DollarSign,
  Gauge,
} from 'lucide-react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface BillUploadFormProps {
  connectionId: string
  onUploadComplete: () => void
  onComplete: () => void
}

interface ExtractedData {
  rate_per_kwh: number | null
  supplier_name: string | null
  period_start: string | null
  period_end: string | null
  usage_kwh: number | null
  amount: number | null
  currency: string
}

interface ParseResult {
  status: 'pending' | 'processing' | 'complete' | 'failed'
  extracted_data: ExtractedData | null
  error_message: string | null
}

const ACCEPTED_TYPES = [
  'application/pdf',
  'image/png',
  'image/jpeg',
  'image/jpg',
]

const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10 MB

const FILE_TYPE_ICONS: Record<string, React.ElementType> = {
  'application/pdf': FileText,
  'image/png': ImageIcon,
  'image/jpeg': ImageIcon,
  'image/jpg': ImageIcon,
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function formatCurrency(amount: number, currency: string): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency || 'USD',
  }).format(amount)
}

export function BillUploadForm({
  connectionId,
  onUploadComplete,
  onComplete,
}: BillUploadFormProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [dragActive, setDragActive] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [parseResult, setParseResult] = useState<ParseResult | null>(null)
  const [pollCount, setPollCount] = useState(0)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Clean up polling on unmount
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current)
      }
    }
  }, [])

  const validateFile = useCallback((file: File): string | null => {
    if (!ACCEPTED_TYPES.includes(file.type)) {
      return 'Unsupported file type. Please upload a PDF, PNG, or JPG file.'
    }
    if (file.size > MAX_FILE_SIZE) {
      return `File is too large (${formatFileSize(file.size)}). Maximum size is 10 MB.`
    }
    return null
  }, [])

  const handleFileSelect = useCallback(
    (file: File) => {
      const validationError = validateFile(file)
      if (validationError) {
        setError(validationError)
        setSelectedFile(null)
        return
      }
      setError(null)
      setSelectedFile(file)
      // Reset any previous upload state
      setParseResult(null)
      setUploadProgress(0)
    },
    [validateFile]
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragActive(false)
      const file = e.dataTransfer.files[0]
      if (file) {
        handleFileSelect(file)
      }
    },
    [handleFileSelect]
  )

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragActive(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragActive(false)
  }, [])

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) {
        handleFileSelect(file)
      }
    },
    [handleFileSelect]
  )

  const pollParseStatus = useCallback(
    async (uploadId: string) => {
      let attempts = 0
      const maxAttempts = 60 // 2 minutes at 2-second intervals

      pollIntervalRef.current = setInterval(async () => {
        attempts++
        setPollCount(attempts)

        if (attempts >= maxAttempts) {
          if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current)
          }
          setParseResult({
            status: 'failed',
            extracted_data: null,
            error_message:
              'Processing timed out. The bill may be taking longer than expected. Please try again.',
          })
          return
        }

        try {
          const res = await fetch(
            `${API_BASE}/api/v1/connections/${connectionId}/uploads/${uploadId}/status`,
            { credentials: 'include' }
          )

          if (res.ok) {
            const data: ParseResult = await res.json()
            setParseResult(data)

            if (data.status === 'complete' || data.status === 'failed') {
              if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current)
              }
              if (data.status === 'complete') {
                onUploadComplete()
              }
            }
          }
        } catch {
          // Silently retry on network errors during polling
        }
      }, 2000)
    },
    [connectionId, onUploadComplete]
  )

  const handleUpload = useCallback(async () => {
    if (!selectedFile) {
      setError('Please select a file first')
      return
    }

    try {
      setUploading(true)
      setError(null)
      setUploadProgress(0)
      setParseResult(null)

      const formData = new FormData()
      formData.append('file', selectedFile)

      // Use XMLHttpRequest for upload progress tracking
      const uploadResult = await new Promise<{ upload_id: string }>(
        (resolve, reject) => {
          const xhr = new XMLHttpRequest()

          xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
              const pct = Math.round((e.loaded / e.total) * 100)
              setUploadProgress(pct)
            }
          })

          xhr.addEventListener('load', () => {
            if (xhr.status >= 200 && xhr.status < 300) {
              try {
                resolve(JSON.parse(xhr.responseText))
              } catch {
                reject(new Error('Invalid response from server'))
              }
            } else if (xhr.status === 403) {
              reject(new Error('__UPGRADE__'))
            } else {
              try {
                const errData = JSON.parse(xhr.responseText)
                reject(new Error(errData.detail || 'Upload failed'))
              } catch {
                reject(new Error('Upload failed. Please try again.'))
              }
            }
          })

          xhr.addEventListener('error', () => {
            reject(new Error('Network error. Please check your connection.'))
          })

          xhr.addEventListener('abort', () => {
            reject(new Error('Upload was cancelled.'))
          })

          xhr.open(
            'POST',
            `${API_BASE}/api/v1/connections/${connectionId}/upload`
          )
          xhr.withCredentials = true
          xhr.send(formData)
        }
      )

      // Upload complete, start polling for parse status
      setUploadProgress(100)
      setParseResult({ status: 'pending', extracted_data: null, error_message: null })
      pollParseStatus(uploadResult.upload_id)
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Upload failed. Please try again.'
      if (message === '__UPGRADE__') {
        setError(
          'Bill upload is available on Pro and Business plans. Please upgrade to continue.'
        )
      } else {
        setError(message)
      }
    } finally {
      setUploading(false)
    }
  }, [selectedFile, connectionId, pollParseStatus])

  const clearFile = () => {
    setSelectedFile(null)
    setError(null)
    setParseResult(null)
    setUploadProgress(0)
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current)
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleRetry = () => {
    setParseResult(null)
    setUploadProgress(0)
    setError(null)
    handleUpload()
  }

  // Parse result states
  const isProcessing =
    parseResult?.status === 'pending' || parseResult?.status === 'processing'
  const isComplete = parseResult?.status === 'complete'
  const isFailed = parseResult?.status === 'failed'

  return (
    <Card padding="lg">
      <div className="flex items-center gap-3 mb-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-warning-100">
          <Upload className="h-5 w-5 text-warning-600" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            Upload Utility Bill
          </h2>
          <p className="text-sm text-gray-500">
            Upload your bill and we will extract rate data using document
            analysis
          </p>
        </div>
      </div>

      <div className="space-y-6">
        {/* Drop zone - hide when processing or complete */}
        {!isProcessing && !isComplete && (
          <>
            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onClick={() => fileInputRef.current?.click()}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  fileInputRef.current?.click()
                }
              }}
              role="button"
              tabIndex={0}
              aria-label="Upload a bill file"
              className={cn(
                'flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-8',
                'transition-colors duration-200',
                'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
                dragActive
                  ? 'border-primary-400 bg-primary-50'
                  : 'border-gray-300 bg-gray-50 hover:border-gray-400 hover:bg-gray-100'
              )}
            >
              <Upload
                className={cn(
                  'h-8 w-8',
                  dragActive ? 'text-primary-500' : 'text-gray-400'
                )}
              />
              <p className="mt-3 text-sm font-medium text-gray-700">
                {dragActive
                  ? 'Drop file here'
                  : 'Drag and drop your bill here'}
              </p>
              <p className="mt-1 text-xs text-gray-500">
                or click to browse files
              </p>
              <div className="mt-3 flex items-center gap-2">
                <Badge variant="default">PDF</Badge>
                <Badge variant="default">PNG</Badge>
                <Badge variant="default">JPG</Badge>
              </div>
              <p className="mt-2 text-xs text-gray-400">
                Max file size: 10 MB
              </p>
            </div>

            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg"
              onChange={handleInputChange}
              className="hidden"
              aria-hidden="true"
            />
          </>
        )}

        {/* Selected file preview */}
        {selectedFile && !isComplete && (
          <div className="flex items-center justify-between rounded-lg border border-gray-200 bg-white p-3">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-100">
                {React.createElement(
                  FILE_TYPE_ICONS[selectedFile.type] || File,
                  { className: 'h-5 w-5 text-gray-500' }
                )}
              </div>
              <div>
                <p className="text-sm font-medium text-gray-900">
                  {selectedFile.name}
                </p>
                <p className="text-xs text-gray-500">
                  {formatFileSize(selectedFile.size)} &middot;{' '}
                  {selectedFile.type === 'application/pdf'
                    ? 'PDF'
                    : selectedFile.type.split('/')[1]?.toUpperCase()}
                </p>
              </div>
            </div>
            {!uploading && !isProcessing && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  clearFile()
                }}
                className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
                aria-label="Remove selected file"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        )}

        {/* Upload progress bar */}
        {(uploading || (uploadProgress > 0 && uploadProgress < 100)) && (
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
        )}

        {/* Processing status */}
        {isProcessing && (
          <div className="flex flex-col items-center justify-center rounded-xl border border-primary-200 bg-primary-50 p-8">
            <Loader2 className="h-8 w-8 animate-spin text-primary-500" />
            <p className="mt-4 text-sm font-medium text-primary-700">
              {parseResult?.status === 'pending'
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
        )}

        {/* Extracted data on success */}
        {isComplete && parseResult?.extracted_data && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 rounded-lg border border-success-200 bg-success-50 p-3">
              <CheckCircle2 className="h-5 w-5 text-success-500 shrink-0" />
              <p className="text-sm font-medium text-success-700">
                Bill processed successfully
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              {parseResult.extracted_data.rate_per_kwh !== null && (
                <ExtractedField
                  icon={Zap}
                  label="Rate"
                  value={`${(parseResult.extracted_data.rate_per_kwh * 100).toFixed(2)} c/kWh`}
                  highlight
                />
              )}
              {parseResult.extracted_data.supplier_name && (
                <ExtractedField
                  icon={File}
                  label="Supplier"
                  value={parseResult.extracted_data.supplier_name}
                />
              )}
              {parseResult.extracted_data.period_start &&
                parseResult.extracted_data.period_end && (
                  <ExtractedField
                    icon={Calendar}
                    label="Period"
                    value={`${formatDate(parseResult.extracted_data.period_start)} - ${formatDate(parseResult.extracted_data.period_end)}`}
                  />
                )}
              {parseResult.extracted_data.usage_kwh !== null && (
                <ExtractedField
                  icon={Gauge}
                  label="Usage"
                  value={`${parseResult.extracted_data.usage_kwh.toLocaleString()} kWh`}
                />
              )}
              {parseResult.extracted_data.amount !== null && (
                <ExtractedField
                  icon={DollarSign}
                  label="Amount"
                  value={formatCurrency(
                    parseResult.extracted_data.amount,
                    parseResult.extracted_data.currency
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
                onClick={() => {
                  clearFile()
                }}
              >
                Upload Another
              </Button>
            </div>
          </div>
        )}

        {/* Parse failure */}
        {isFailed && (
          <div className="space-y-4">
            <div className="flex items-start gap-2 rounded-lg border border-danger-200 bg-danger-50 p-4">
              <AlertCircle className="mt-0.5 h-5 w-5 text-danger-500 shrink-0" />
              <div>
                <p className="text-sm font-medium text-danger-700">
                  Failed to process bill
                </p>
                <p className="mt-1 text-sm text-danger-600">
                  {parseResult?.error_message ||
                    'We could not extract data from this file. Please ensure it is a clear utility bill.'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Button variant="primary" onClick={handleRetry}>
                <RotateCcw className="h-4 w-4" />
                Retry Upload
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  clearFile()
                }}
              >
                Choose Different File
              </Button>
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-danger-200 bg-danger-50 p-3">
            <AlertCircle className="mt-0.5 h-4 w-4 text-danger-500 shrink-0" />
            <p className="text-sm text-danger-700">{error}</p>
          </div>
        )}

        {/* Upload button - only show before upload/processing */}
        {!uploading && !isProcessing && !isComplete && !isFailed && (
          <Button
            variant="primary"
            className="w-full"
            onClick={handleUpload}
            disabled={!selectedFile}
          >
            <Upload className="h-4 w-4" />
            Upload Bill
          </Button>
        )}
      </div>
    </Card>
  )
}

function ExtractedField({
  icon: Icon,
  label,
  value,
  highlight = false,
}: {
  icon: React.ElementType
  label: string
  value: string
  highlight?: boolean
}) {
  return (
    <div
      className={cn(
        'flex items-start gap-3 rounded-lg border p-3',
        highlight
          ? 'border-primary-200 bg-primary-50'
          : 'border-gray-200 bg-gray-50'
      )}
    >
      <div
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
          highlight ? 'bg-primary-100' : 'bg-gray-100'
        )}
      >
        <Icon
          className={cn(
            'h-4 w-4',
            highlight ? 'text-primary-600' : 'text-gray-500'
          )}
        />
      </div>
      <div className="min-w-0">
        <p className="text-xs text-gray-500">{label}</p>
        <p
          className={cn(
            'text-sm font-semibold truncate',
            highlight ? 'text-primary-900' : 'text-gray-900'
          )}
        >
          {value}
        </p>
      </div>
    </div>
  )
}
