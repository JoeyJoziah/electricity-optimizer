'use client'

import React from 'react'
import { Bell, RefreshCw, Menu } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { useRefreshPrices } from '@/lib/hooks/usePrices'

interface HeaderProps {
  title: string
  onMenuClick?: () => void
}

export function Header({ title, onMenuClick }: HeaderProps) {
  const refreshPrices = useRefreshPrices()
  const [isRefreshing, setIsRefreshing] = React.useState(false)

  const handleRefresh = async () => {
    setIsRefreshing(true)
    refreshPrices()
    // Simulate delay for UX
    setTimeout(() => setIsRefreshing(false), 1000)
  }

  return (
    <header className="sticky top-0 z-40 flex h-16 items-center justify-between border-b border-gray-200 bg-white px-4 lg:px-6">
      {/* Left side */}
      <div className="flex items-center gap-4">
        <Button
          variant="ghost"
          size="sm"
          className="lg:hidden"
          onClick={onMenuClick}
          aria-label="Open menu"
        >
          <Menu className="h-5 w-5" />
        </Button>
        <h1 className="text-xl font-semibold text-gray-900">{title}</h1>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-3">
        {/* Realtime indicator */}
        <div
          data-testid="realtime-indicator"
          className="hidden items-center gap-2 text-sm text-gray-500 sm:flex"
        >
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success-400 opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-success-500" />
          </span>
          <span>Live</span>
        </div>

        {/* Refresh button */}
        <Button
          variant="ghost"
          size="sm"
          onClick={handleRefresh}
          disabled={isRefreshing}
          aria-label="Refresh data"
        >
          <RefreshCw
            className={cn(
              'h-4 w-4',
              isRefreshing && 'animate-spin'
            )}
          />
        </Button>

        {/* Notifications */}
        <Button
          variant="ghost"
          size="sm"
          className="relative"
          aria-label="View notifications"
        >
          <Bell className="h-5 w-5" />
          <Badge
            variant="danger"
            className="absolute -right-1 -top-1 h-4 min-w-4 px-1 text-xs"
          >
            3
          </Badge>
        </Button>
      </div>
    </header>
  )
}

// Import cn for the component
import { cn } from '@/lib/utils/cn'
