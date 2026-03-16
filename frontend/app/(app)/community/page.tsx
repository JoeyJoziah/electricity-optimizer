'use client'

import React from 'react'
import { CommunityStats } from '@/components/community/CommunityStats'
import { PostForm } from '@/components/community/PostForm'
import { PostList } from '@/components/community/PostList'
import { ErrorBoundary } from '@/components/error-boundary'
import { useSettingsStore } from '@/lib/store/settings'
import { useAuth } from '@/lib/hooks/useAuth'

export default function CommunityPage() {
  const { user } = useAuth()
  const utilityTypes = useSettingsStore((s) => s.utilityTypes) || ['electricity']
  const [activeUtility, setActiveUtility] = React.useState<string>(utilityTypes[0] || 'electricity')

  return (
    <div className="flex flex-col">
      <div className="border-b px-6 py-4">
        <h1 className="text-xl font-semibold text-gray-900">Community</h1>
        <p className="text-sm text-gray-500">
          Share tips, report rates, and connect with neighbors
        </p>
      </div>
      <div className="space-y-6 p-6">
        {/* Stats banner */}
        <ErrorBoundary>
          <CommunityStats />
        </ErrorBoundary>

        {/* Utility filter */}
        {utilityTypes.length > 1 && (
          <div className="flex gap-2" data-testid="community-utility-filter">
            {utilityTypes.map((ut: string) => (
              <button
                key={ut}
                onClick={() => setActiveUtility(ut)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                  activeUtility === ut
                    ? 'bg-primary-100 text-primary-700'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
                data-testid={`community-filter-${ut}`}
              >
                {ut.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
              </button>
            ))}
          </div>
        )}

        {/* Post form */}
        <ErrorBoundary>
          <PostForm defaultUtilityType={activeUtility} />
        </ErrorBoundary>

        {/* Post list */}
        <ErrorBoundary>
          <PostList
            utilityType={activeUtility}
            currentUserId={user?.id}
          />
        </ErrorBoundary>
      </div>
    </div>
  )
}
