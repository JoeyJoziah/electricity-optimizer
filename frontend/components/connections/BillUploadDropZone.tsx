import React, { useCallback } from 'react'
import { cn } from '@/lib/utils/cn'
import { Badge } from '@/components/ui/badge'
import { Upload } from 'lucide-react'

interface BillUploadDropZoneProps {
  dragActive: boolean
  fileInputRef: React.RefObject<HTMLInputElement | null>
  onDrop: (e: React.DragEvent) => void
  onDragOver: (e: React.DragEvent) => void
  onDragLeave: (e: React.DragEvent) => void
  onInputChange: (e: React.ChangeEvent<HTMLInputElement>) => void
}

export function BillUploadDropZone({
  dragActive,
  fileInputRef,
  onDrop,
  onDragOver,
  onDragLeave,
  onInputChange,
}: BillUploadDropZoneProps) {
  const handleClick = useCallback(() => {
    fileInputRef.current?.click()
  }, [fileInputRef])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        fileInputRef.current?.click()
      }
    },
    [fileInputRef]
  )

  return (
    <>
      <div
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
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
        ref={fileInputRef as React.RefObject<HTMLInputElement>}
        type="file"
        accept=".pdf,.png,.jpg,.jpeg"
        onChange={onInputChange}
        className="hidden"
        aria-hidden="true"
      />
    </>
  )
}
