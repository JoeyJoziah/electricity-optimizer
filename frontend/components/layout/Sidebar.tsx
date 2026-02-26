'use client'

import React, { useEffect } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils/cn'
import { useAuth } from '@/lib/hooks/useAuth'
import { useSidebar } from '@/lib/contexts/sidebar-context'
import { useSettingsStore } from '@/lib/store/settings'
import {
  LayoutDashboard,
  TrendingUp,
  Building2,
  Link2,
  Calendar,
  Settings,
  Zap,
  LogOut,
  User,
  X,
} from 'lucide-react'

const navigation = [
  { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { name: 'Prices', href: '/prices', icon: TrendingUp },
  { name: 'Suppliers', href: '/suppliers', icon: Building2 },
  { name: 'Connections', href: '/connections', icon: Link2 },
  { name: 'Optimize', href: '/optimize', icon: Calendar },
  { name: 'Settings', href: '/settings', icon: Settings },
]

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname()
  const { user, isAuthenticated, signOut } = useAuth()
  const currentSupplier = useSettingsStore((s) => s.currentSupplier)

  // Setup completion status for nav items
  const setupComplete: Record<string, boolean> = {
    '/suppliers': !!currentSupplier,
  }

  return (
    <>
      {/* Logo */}
      <div className="flex h-16 items-center gap-2 border-b border-gray-200 px-6">
        <Zap className="h-8 w-8 text-primary-600" />
        <span className="text-xl font-bold text-gray-900">
          Electricity Optimizer
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {navigation.map((item) => {
          const isActive = pathname === item.href
          return (
            <Link
              key={item.name}
              href={item.href}
              onClick={onNavigate}
              className={cn(
                'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary-50 text-primary-700'
                  : 'text-gray-700 hover:bg-gray-100 hover:text-gray-900'
              )}
            >
              <item.icon
                className={cn(
                  'h-5 w-5',
                  isActive ? 'text-primary-600' : 'text-gray-400'
                )}
              />
              {item.name}
              {setupComplete[item.href] && (
                <span className="ml-auto h-2 w-2 rounded-full bg-success-500" title="Set up" />
              )}
            </Link>
          )
        })}
      </nav>

      {/* Footer -- User menu */}
      <div className="border-t border-gray-200 p-4">
        {isAuthenticated && user ? (
          <div className="space-y-3">
            <div className="flex items-center gap-3 rounded-lg px-3 py-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-100">
                <User className="h-4 w-4 text-primary-600" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-gray-900">
                  {user.name || 'User'}
                </p>
                <p className="truncate text-xs text-gray-500">{user.email}</p>
              </div>
            </div>
            <button
              onClick={() => signOut()}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 hover:text-gray-900 transition-colors"
            >
              <LogOut className="h-5 w-5 text-gray-400" />
              Sign out
            </button>
          </div>
        ) : (
          <div className="rounded-lg bg-primary-50 p-3">
            <p className="text-sm font-medium text-primary-900">
              Need help?
            </p>
            <p className="mt-1 text-xs text-primary-700">
              Check our documentation or contact support
            </p>
          </div>
        )}
      </div>
    </>
  )
}

export function Sidebar() {
  const { isOpen, close } = useSidebar()
  const pathname = usePathname()

  // Close mobile sidebar on route change
  useEffect(() => {
    close()
  }, [pathname, close])

  return (
    <>
      {/* Desktop sidebar -- always visible on lg+ screens */}
      <aside className="fixed inset-y-0 left-0 z-50 hidden w-64 flex-col border-r border-gray-200 bg-white lg:flex">
        <SidebarContent />
      </aside>

      {/* Mobile sidebar overlay -- visible only when open on small screens */}
      {isOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-gray-900/50 transition-opacity"
            onClick={close}
            aria-hidden="true"
          />

          {/* Sidebar panel */}
          <aside className="fixed inset-y-0 left-0 z-50 flex w-64 flex-col bg-white shadow-xl">
            {/* Close button */}
            <button
              onClick={close}
              className="absolute right-3 top-4 rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 focus:outline-none focus:ring-2 focus:ring-primary-500"
              aria-label="Close sidebar"
            >
              <X className="h-5 w-5" />
            </button>

            <SidebarContent onNavigate={close} />
          </aside>
        </div>
      )}
    </>
  )
}
