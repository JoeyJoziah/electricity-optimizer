'use client'

import React, { useState, useRef, useEffect } from 'react'
import { Bell } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api/client'
import { cn } from '@/lib/utils/cn'

interface Notification {
  id: string
  type: string
  title: string
  body: string | null
  created_at: string
}

interface NotificationsResponse {
  notifications: Notification[]
  total: number
}

interface CountResponse {
  unread: number
}

export function NotificationBell() {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const queryClient = useQueryClient()

  // Poll the unread count every 30 seconds so the badge stays current
  const { data: countData } = useQuery<CountResponse>({
    queryKey: ['notifications', 'count'],
    queryFn: () => apiClient.get<CountResponse>('/notifications/count'),
    refetchInterval: 30_000,
  })

  // Only fetch the full list when the panel is open
  const { data: notifData } = useQuery<NotificationsResponse>({
    queryKey: ['notifications'],
    queryFn: () => apiClient.get<NotificationsResponse>('/notifications'),
    enabled: open,
  })

  const markRead = useMutation<unknown, unknown, string>({
    mutationFn: (id: string) =>
      apiClient.put<unknown>(`/notifications/${id}/read`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
      queryClient.invalidateQueries({ queryKey: ['notifications', 'count'] })
    },
  })

  // Close the panel when clicking outside
  useEffect(() => {
    if (!open) return

    function handleClickOutside(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  const unreadCount = countData?.unread ?? 0

  return (
    <div className="relative" ref={containerRef}>
      <button
        onClick={() => setOpen((prev) => !prev)}
        className="relative rounded-full p-2 hover:bg-gray-100"
        aria-label={
          unreadCount > 0
            ? `Notifications (${unreadCount} unread)`
            : 'Notifications'
        }
        aria-expanded={open}
      >
        <Bell className="h-5 w-5 text-gray-600" />
        {unreadCount > 0 && (
          <span
            aria-hidden="true"
            className={cn(
              'absolute -right-1 -top-1 flex items-center justify-center',
              'h-5 w-5 rounded-full bg-red-600 text-xs font-semibold text-white',
            )}
          >
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Notifications panel"
          className="absolute right-0 top-full z-50 mt-2 w-80 rounded-lg border border-gray-200 bg-white shadow-lg"
        >
          <div className="border-b border-gray-200 px-4 py-3">
            <h3 className="text-sm font-semibold text-gray-900">
              Notifications
            </h3>
          </div>

          <div className="max-h-80 overflow-y-auto">
            {notifData?.notifications?.length ? (
              notifData.notifications.map((n) => (
                <button
                  key={n.id}
                  onClick={() => {
                    markRead.mutate(n.id)
                  }}
                  className="w-full border-b border-gray-100 px-4 py-3 text-left last:border-0 hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500"
                >
                  <p className="text-sm font-medium text-gray-900">
                    {n.title}
                  </p>
                  {n.body && (
                    <p className="mt-0.5 text-xs text-gray-500">{n.body}</p>
                  )}
                </button>
              ))
            ) : (
              <p className="px-4 py-6 text-center text-sm text-gray-500">
                No new notifications
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
