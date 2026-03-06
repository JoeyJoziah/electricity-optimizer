'use client'

import React, { useState, useRef, useCallback, useEffect } from 'react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { API_ORIGIN } from '@/lib/config/env'
import { Upload, AlertCircle } from 'lucide-react'
import { ACCEPTED_TYPES, MAX_FILE_SIZE, formatFileSize } from './BillUploadTypes'
import type { BillUploadFormProps, ParseResult } from './BillUploadTypes'
import { BillUploadDropZone } from './BillUploadDropZone'
import { BillUploadFilePreview } from './BillUploadFilePreview'
import { BillUploadProgressBar, BillUploadProcessingStatus } from './BillUploadProgress'
import { BillUploadSuccess, BillUploadFailure } from './BillUploadResults'

export type { BillUploadFormProps }

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
            `${API_ORIGIN}/api/v1/connections/${connectionId}/uploads/${uploadId}`,
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
            `${API_ORIGIN}/api/v1/connections/${connectionId}/upload`
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
          <BillUploadDropZone
            dragActive={dragActive}
            fileInputRef={fileInputRef}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onInputChange={handleInputChange}
          />
        )}

        {/* Selected file preview */}
        {selectedFile && !isComplete && (
          <BillUploadFilePreview
            file={selectedFile}
            uploading={uploading}
            isProcessing={!!isProcessing}
            onClear={clearFile}
          />
        )}

        {/* Upload progress bar */}
        <BillUploadProgressBar
          uploading={uploading}
          uploadProgress={uploadProgress}
        />

        {/* Processing status */}
        {isProcessing && parseResult && (
          <BillUploadProcessingStatus
            parseResult={parseResult}
            pollCount={pollCount}
          />
        )}

        {/* Extracted data on success */}
        {isComplete && parseResult?.extracted_data && (
          <BillUploadSuccess
            extractedData={parseResult.extracted_data}
            onComplete={onComplete}
            onClearFile={clearFile}
          />
        )}

        {/* Parse failure */}
        {isFailed && (
          <BillUploadFailure
            errorMessage={parseResult?.error_message || null}
            onRetry={handleRetry}
            onClearFile={clearFile}
          />
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
