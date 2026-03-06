import React from 'react'
import { X, File } from 'lucide-react'
import { FILE_TYPE_ICONS, formatFileSize } from './BillUploadTypes'

interface BillUploadFilePreviewProps {
  file: File
  uploading: boolean
  isProcessing: boolean
  onClear: () => void
}

export function BillUploadFilePreview({
  file,
  uploading,
  isProcessing,
  onClear,
}: BillUploadFilePreviewProps) {
  const IconComponent = FILE_TYPE_ICONS[file.type] || File

  return (
    <div className="flex items-center justify-between rounded-lg border border-gray-200 bg-white p-3">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-100">
          {React.createElement(IconComponent, {
            className: 'h-5 w-5 text-gray-500',
          })}
        </div>
        <div>
          <p className="text-sm font-medium text-gray-900">{file.name}</p>
          <p className="text-xs text-gray-500">
            {formatFileSize(file.size)} &middot;{' '}
            {file.type === 'application/pdf'
              ? 'PDF'
              : file.type.split('/')[1]?.toUpperCase()}
          </p>
        </div>
      </div>
      {!uploading && !isProcessing && (
        <button
          onClick={(e) => {
            e.stopPropagation()
            onClear()
          }}
          className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
          aria-label="Remove selected file"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  )
}
