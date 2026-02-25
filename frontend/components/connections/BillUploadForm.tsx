'use client'

import React, { useState, useRef, useCallback } from 'react'
import { cn } from '@/lib/utils/cn'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Upload,
  FileText,
  X,
  AlertCircle,
  Clock,
} from 'lucide-react'

interface BillUploadFormProps {
  onComplete: () => void
}

const ACCEPTED_TYPES = [
  'application/pdf',
  'image/png',
  'image/jpeg',
  'image/jpg',
]

const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10 MB

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function BillUploadForm({ onComplete }: BillUploadFormProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [dragActive, setDragActive] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showComingSoon, setShowComingSoon] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

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

  const handleUpload = () => {
    if (!selectedFile) {
      setError('Please select a file first')
      return
    }
    // Phase 1: Show "Coming Soon" — real upload endpoint wired in Phase 2
    setShowComingSoon(true)
  }

  const clearFile = () => {
    setSelectedFile(null)
    setError(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  if (showComingSoon) {
    return (
      <Card className="p-8 text-center">
        <Clock className="mx-auto h-12 w-12 text-primary-400" />
        <h3 className="mt-4 text-lg font-semibold text-gray-900">
          Coming Soon
        </h3>
        <p className="mt-2 text-sm text-gray-500">
          Bill upload and automated extraction is launching in the next release.
          We will notify you when it is available.
        </p>
        <Button variant="outline" className="mt-6" onClick={onComplete}>
          Back to Connections
        </Button>
      </Card>
    )
  }

  return (
    <Card padding="lg">
      <div className="flex items-center gap-3 mb-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-warning-100">
          <Upload className="h-5 w-5 text-warning-600" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            Upload Utility Bills
          </h2>
          <p className="text-sm text-gray-500">
            Upload your bills and we will extract rate data using document
            analysis
          </p>
        </div>
      </div>

      <div className="space-y-6">
        {/* Drop zone */}
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
            {dragActive ? 'Drop file here' : 'Drag and drop your bill here'}
          </p>
          <p className="mt-1 text-xs text-gray-500">
            or click to browse files
          </p>
          <div className="mt-3 flex items-center gap-2">
            <Badge variant="default">PDF</Badge>
            <Badge variant="default">PNG</Badge>
            <Badge variant="default">JPG</Badge>
          </div>
          <p className="mt-2 text-xs text-gray-400">Max file size: 10 MB</p>
        </div>

        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg"
          onChange={handleInputChange}
          className="hidden"
          aria-hidden="true"
        />

        {/* Selected file */}
        {selectedFile && (
          <div className="flex items-center justify-between rounded-lg border border-gray-200 bg-white p-3">
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded bg-gray-100">
                <FileText className="h-4 w-4 text-gray-500" />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-900">
                  {selectedFile.name}
                </p>
                <p className="text-xs text-gray-500">
                  {formatFileSize(selectedFile.size)}
                </p>
              </div>
            </div>
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
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-danger-200 bg-danger-50 p-3">
            <AlertCircle className="mt-0.5 h-4 w-4 text-danger-500 shrink-0" />
            <p className="text-sm text-danger-700">{error}</p>
          </div>
        )}

        {/* Upload button */}
        <div className="flex items-center gap-3">
          <Button
            variant="primary"
            className="flex-1"
            onClick={handleUpload}
            disabled={!selectedFile}
          >
            <Upload className="h-4 w-4" />
            Upload Bill
          </Button>
          <Badge variant="info">Phase 2</Badge>
        </div>
      </div>
    </Card>
  )
}
