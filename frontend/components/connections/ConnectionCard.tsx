'use client'

import React, { useState, useRef, useEffect } from 'react'
import { cn } from '@/lib/utils/cn'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { formatRelativeTime } from '@/lib/utils/format'
import { apiClient } from '@/lib/api/client'
import {
  KeyRound,
  Mail,
  Upload,
  Globe,
  Trash2,
  RefreshCw,
  AlertTriangle,
  Zap,
  ChevronRight,
  Pencil,
  Check,
  X,
  Loader2,
} from 'lucide-react'

interface Connection {
  id: string
  method: string
  status: string
  supplier_name: string | null
  email_provider: string | null
  last_sync_at: string | null
  last_sync_error: string | null
  current_rate: number | null
  created_at: string
  label?: string | null
}

interface ConnectionCardProps {
  connection: Connection
  onDelete: () => void
  onViewRates?: (connectionId: string) => void
  onRefresh?: () => void
}

const methodIcons: Record<string, React.ElementType> = {
  direct: KeyRound,
  direct_login: KeyRound,
  email_import: Mail,
  email_scan: Mail,
  manual_upload: Upload,
  bill_upload: Upload,
  portal_scrape: Globe,
  utilityapi: Zap,
}

const methodLabels: Record<string, string> = {
  direct: 'Utility Account',
  direct_login: 'Utility Account',
  email_import: 'Email Scan',
  email_scan: 'Email Scan',
  manual_upload: 'Bill Upload',
  bill_upload: 'Bill Upload',
  portal_scrape: 'Portal Connection',
  utilityapi: 'UtilityAPI',
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

export function ConnectionCard({
  connection,
  onDelete,
  onViewRates,
  onRefresh,
}: ConnectionCardProps) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [syncError, setSyncError] = useState<string | null>(null)

  // Editable label state
  const [editing, setEditing] = useState(false)
  const [labelValue, setLabelValue] = useState(connection.label || '')
  const [savingLabel, setSavingLabel] = useState(false)
  const [labelError, setLabelError] = useState<string | null>(null)
  const [currentLabel, setCurrentLabel] = useState(connection.label || null)
  const labelInputRef = useRef<HTMLInputElement>(null)

  const Icon = methodIcons[connection.method] || KeyRound
  const methodLabel = methodLabels[connection.method] || connection.method
  const status = statusConfig[connection.status] || {
    variant: 'default' as const,
    label: connection.status,
  }

  const displayName =
    currentLabel || connection.supplier_name || connection.email_provider || methodLabel

  const canSync =
    connection.method === 'direct_login' ||
    connection.method === 'direct' ||
    connection.method === 'email_scan' ||
    connection.method === 'email_import' ||
    connection.method === 'portal_scrape' ||
    connection.method === 'utilityapi'
  const hasRates = connection.current_rate !== null && connection.current_rate !== undefined
  const hasSyncError = !!connection.last_sync_error

  // Focus input when entering edit mode
  useEffect(() => {
    if (editing && labelInputRef.current) {
      labelInputRef.current.focus()
      labelInputRef.current.select()
    }
  }, [editing])

  const handleStartEditing = () => {
    setLabelValue(currentLabel || '')
    setLabelError(null)
    setEditing(true)
  }

  const handleCancelEditing = () => {
    setEditing(false)
    setLabelValue(currentLabel || '')
    setLabelError(null)
  }

  const handleSaveLabel = async () => {
    const trimmed = labelValue.trim()
    setSavingLabel(true)
    setLabelError(null)

    try {
      await apiClient.patch(`/connections/${connection.id}`, {
        label: trimmed || null,
      })
      setCurrentLabel(trimmed || null)
      setEditing(false)
    } catch {
      setLabelError('Failed to save label')
    } finally {
      setSavingLabel(false)
    }
  }

  const handleLabelKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleSaveLabel()
    } else if (e.key === 'Escape') {
      handleCancelEditing()
    }
  }

  const handleDelete = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true)
      setDeleteError(null)
      return
    }

    try {
      setDeleting(true)
      setDeleteError(null)
      await apiClient.delete(`/connections/${connection.id}`)
      onDelete()
    } catch {
      setDeleteError('Failed to delete connection')
    } finally {
      setDeleting(false)
      setConfirmDelete(false)
    }
  }

  const handleSync = async () => {
    try {
      setSyncing(true)
      setSyncError(null)
      await apiClient.post(`/connections/${connection.id}/sync`)
      if (onRefresh) {
        onRefresh()
      }
    } catch {
      setSyncError('Sync failed. Please try again.')
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div
      className={cn(
        'rounded-xl border bg-white transition-shadow hover:shadow-sm',
        hasSyncError ? 'border-warning-200' : 'border-gray-200'
      )}
      data-testid={`connection-card-${connection.id}`}
    >
      <div className="flex items-center justify-between p-4">
        <div className="flex items-center gap-4 min-w-0">
          <div
            className={cn(
              'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg',
              hasSyncError ? 'bg-warning-100' : 'bg-gray-100'
            )}
          >
            {hasSyncError ? (
              <AlertTriangle className="h-5 w-5 text-warning-500" />
            ) : (
              <Icon className="h-5 w-5 text-gray-500" />
            )}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              {editing ? (
                <div className="flex items-center gap-1.5">
                  <input
                    ref={labelInputRef}
                    type="text"
                    value={labelValue}
                    onChange={(e) => setLabelValue(e.target.value)}
                    onKeyDown={handleLabelKeyDown}
                    placeholder={
                      connection.supplier_name ||
                      connection.email_provider ||
                      methodLabel
                    }
                    maxLength={100}
                    disabled={savingLabel}
                    className="rounded bg-white border border-gray-300 px-2 py-0.5 text-sm font-medium text-gray-900 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 focus:outline-none disabled:opacity-50 w-48"
                    aria-label="Connection label"
                    data-testid="label-input"
                  />
                  {savingLabel ? (
                    <Loader2 className="h-4 w-4 animate-spin text-gray-400" />
                  ) : (
                    <>
                      <button
                        onClick={handleSaveLabel}
                        className="rounded p-0.5 text-success-600 hover:bg-success-50 transition-colors"
                        aria-label="Save label"
                        data-testid="save-label"
                      >
                        <Check className="h-4 w-4" />
                      </button>
                      <button
                        onClick={handleCancelEditing}
                        className="rounded p-0.5 text-gray-400 hover:bg-gray-100 transition-colors"
                        aria-label="Cancel editing"
                        data-testid="cancel-label"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </>
                  )}
                </div>
              ) : (
                <>
                  <p className="font-medium text-gray-900 truncate">
                    {displayName}
                  </p>
                  <button
                    onClick={handleStartEditing}
                    className="rounded p-0.5 text-gray-300 hover:text-gray-500 hover:bg-gray-100 transition-colors"
                    aria-label="Edit label"
                    data-testid="edit-label"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                </>
              )}
              <Badge variant={status.variant}>{status.label}</Badge>
            </div>
            {labelError && (
              <p className="text-xs text-danger-600 mt-0.5">{labelError}</p>
            )}
            <div className="flex items-center gap-3 text-xs text-gray-500">
              <span>{methodLabel}</span>
              {connection.last_sync_at && (
                <>
                  <span aria-hidden="true">&#183;</span>
                  <span className="flex items-center gap-1">
                    <RefreshCw className="h-3 w-3" />
                    Synced {formatRelativeTime(connection.last_sync_at)}
                  </span>
                </>
              )}
              {hasRates && (
                <>
                  <span aria-hidden="true">&#183;</span>
                  <span className="flex items-center gap-1 font-medium text-primary-600">
                    <Zap className="h-3 w-3" />
                    {(connection.current_rate! * 100).toFixed(2)} c/kWh
                  </span>
                </>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0 ml-4">
          {/* Sync button for direct/email connections */}
          {canSync && connection.status === 'active' && (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleSync}
              loading={syncing}
              disabled={syncing}
              aria-label={`Sync ${displayName}`}
            >
              <RefreshCw
                className={cn(
                  'h-4 w-4 text-gray-400',
                  syncing && 'animate-spin'
                )}
              />
            </Button>
          )}

          {/* View Rates button */}
          {onViewRates && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onViewRates(connection.id)}
              aria-label={`View rates for ${displayName}`}
            >
              <ChevronRight className="h-4 w-4 text-gray-400" />
            </Button>
          )}

          {/* Delete */}
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

      {/* Sync error banner */}
      {hasSyncError && (
        <div className="flex items-center gap-2 border-t border-warning-200 bg-warning-50 px-4 py-2">
          <AlertTriangle className="h-3.5 w-3.5 text-warning-500 shrink-0" />
          <p className="text-xs text-warning-700 truncate">
            {connection.last_sync_error}
          </p>
          {canSync && (
            <Button
              variant="ghost"
              size="sm"
              className="ml-auto shrink-0 text-xs text-warning-700 hover:text-warning-900"
              onClick={handleSync}
              loading={syncing}
            >
              Retry
            </Button>
          )}
        </div>
      )}

      {/* Inline error feedback */}
      {(deleteError || syncError) && (
        <div className="border-t border-danger-200 bg-danger-50 px-4 py-2">
          <p className="text-xs text-danger-700">
            {deleteError || syncError}
          </p>
        </div>
      )}
    </div>
  )
}
