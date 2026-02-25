'use client'

import React, { useState } from 'react'
import { cn } from '@/lib/utils/cn'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { KeyRound, Mail, Upload, Trash2, RefreshCw } from 'lucide-react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface Connection {
  id: string
  method: string
  status: string
  supplier_name: string | null
  email_provider: string | null
  last_sync_at: string | null
  created_at: string
}

interface ConnectionCardProps {
  connection: Connection
  onDelete: () => void
}

const methodIcons: Record<string, React.ElementType> = {
  direct_login: KeyRound,
  email_scan: Mail,
  bill_upload: Upload,
}

const methodLabels: Record<string, string> = {
  direct_login: 'Utility Account',
  email_scan: 'Email Scan',
  bill_upload: 'Bill Upload',
}

const statusConfig: Record<
  string,
  { variant: 'success' | 'warning' | 'danger' | 'default' | 'info'; label: string }
> = {
  active: { variant: 'success', label: 'Active' },
  pending: { variant: 'warning', label: 'Pending' },
  syncing: { variant: 'info', label: 'Syncing' },
  failed: { variant: 'danger', label: 'Failed' },
  expired: { variant: 'default', label: 'Expired' },
  revoked: { variant: 'default', label: 'Revoked' },
}

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSeconds = Math.floor(diffMs / 1000)
  const diffMinutes = Math.floor(diffSeconds / 60)
  const diffHours = Math.floor(diffMinutes / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffSeconds < 60) return 'just now'
  if (diffMinutes < 60) return `${diffMinutes}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 30) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

export function ConnectionCard({ connection, onDelete }: ConnectionCardProps) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const Icon = methodIcons[connection.method] || KeyRound
  const methodLabel = methodLabels[connection.method] || connection.method
  const status = statusConfig[connection.status] || {
    variant: 'default' as const,
    label: connection.status,
  }

  const displayName =
    connection.supplier_name ||
    connection.email_provider ||
    methodLabel

  const handleDelete = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true)
      return
    }

    try {
      setDeleting(true)
      const res = await fetch(
        `${API_BASE}/api/v1/connections/${connection.id}`,
        {
          method: 'DELETE',
          credentials: 'include',
        }
      )
      if (res.ok) {
        onDelete()
      }
    } catch {
      // Silently fail - user can retry
    } finally {
      setDeleting(false)
      setConfirmDelete(false)
    }
  }

  return (
    <div
      className={cn(
        'flex items-center justify-between rounded-xl border border-gray-200 bg-white p-4',
        'transition-shadow hover:shadow-sm'
      )}
      data-testid={`connection-card-${connection.id}`}
    >
      <div className="flex items-center gap-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-100">
          <Icon className="h-5 w-5 text-gray-500" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <p className="font-medium text-gray-900">{displayName}</p>
            <Badge variant={status.variant}>{status.label}</Badge>
          </div>
          <div className="flex items-center gap-3 text-xs text-gray-500">
            <span>{methodLabel}</span>
            {connection.last_sync_at && (
              <>
                <span aria-hidden="true">&#183;</span>
                <span className="flex items-center gap-1">
                  <RefreshCw className="h-3 w-3" />
                  {formatRelativeTime(connection.last_sync_at)}
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {confirmDelete ? (
          <div className="flex items-center gap-2">
            <span className="text-xs text-danger-600">Confirm?</span>
            <Button
              variant="danger"
              size="sm"
              loading={deleting}
              onClick={handleDelete}
            >
              Delete
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setConfirmDelete(false)}
            >
              Cancel
            </Button>
          </div>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleDelete}
            aria-label={`Delete ${displayName} connection`}
          >
            <Trash2 className="h-4 w-4 text-gray-400 hover:text-danger-500 transition-colors" />
          </Button>
        )}
      </div>
    </div>
  )
}
