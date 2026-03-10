/**
 * Notifications API functions
 *
 * CRUD operations for in-app user notifications:
 * - list unread notifications
 * - get unread count (for bell badge polling)
 * - mark individual notification as read
 * - mark all notifications as read (client-side batch)
 */

import { apiClient } from './client'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Notification {
  id: string
  type: string
  title: string
  body: string | null
  created_at: string
}

export interface GetNotificationsResponse {
  notifications: Notification[]
  total: number
}

export interface GetNotificationCountResponse {
  unread: number
}

export interface MarkReadResponse {
  success: boolean
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/**
 * Get unread notifications for the current user (newest first, max 50)
 */
export async function getNotifications(): Promise<GetNotificationsResponse> {
  return apiClient.get<GetNotificationsResponse>('/notifications')
}

/**
 * Get the unread notification count for the current user.
 * Designed to be polled frequently (e.g. every 30s) for the bell badge.
 */
export async function getNotificationCount(): Promise<GetNotificationCountResponse> {
  return apiClient.get<GetNotificationCountResponse>('/notifications/count')
}

/**
 * Mark a single notification as read.
 * Returns 404 if the notification does not exist or is already read.
 */
export async function markNotificationRead(id: string): Promise<MarkReadResponse> {
  return apiClient.put<MarkReadResponse>(`/notifications/${id}/read`, {})
}

/**
 * Mark all currently unread notifications as read.
 *
 * The backend does not expose a bulk-mark-all endpoint, so this function
 * fetches the current list and marks each one individually.  It settles all
 * requests in parallel and ignores individual failures (e.g. 404 for a
 * notification that was already read by another tab).
 */
export async function markAllRead(): Promise<void> {
  const data = await getNotifications()
  await Promise.allSettled(
    data.notifications.map((n) => markNotificationRead(n.id))
  )
}
