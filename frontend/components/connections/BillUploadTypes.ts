import React from 'react'
import { FileText, Image as ImageIcon } from 'lucide-react'

export interface BillUploadFormProps {
  connectionId: string
  onUploadComplete: () => void
  onComplete: () => void
}

export interface ExtractedData {
  rate_per_kwh: number | null
  supplier_name: string | null
  period_start: string | null
  period_end: string | null
  usage_kwh: number | null
  amount: number | null
  currency: string
}

export interface ParseResult {
  status: 'pending' | 'processing' | 'complete' | 'failed'
  extracted_data: ExtractedData | null
  error_message: string | null
}

export const ACCEPTED_TYPES = [
  'application/pdf',
  'image/png',
  'image/jpeg',
  'image/jpg',
]

export const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10 MB

export const FILE_TYPE_ICONS: Record<string, React.ElementType> = {
  'application/pdf': FileText,
  'image/png': ImageIcon,
  'image/jpeg': ImageIcon,
  'image/jpg': ImageIcon,
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

export function formatCurrency(amount: number, currency: string): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency || 'USD',
  }).format(amount)
}
