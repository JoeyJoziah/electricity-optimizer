'use client'

import React from 'react'
import { Skeleton } from '@/components/ui/skeleton'
import { useCommunityPosts } from '@/lib/hooks/useCommunity'
import { useSettingsStore } from '@/lib/store/settings'
import { VoteButton } from './VoteButton'
import { ReportButton } from './ReportButton'
import type { CommunityPost } from '@/lib/api/community'

const POST_TYPE_LABELS: Record<string, string> = {
  tip: 'Tip',
  rate_report: 'Rate Report',
  discussion: 'Discussion',
  review: 'Review',
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

interface PostListProps {
  utilityType: string
  currentUserId?: string
  onEditPost?: (post: CommunityPost) => void
}

export function PostList({ utilityType, currentUserId, onEditPost }: PostListProps) {
  const region = useSettingsStore((s) => s.region)
  const [page, setPage] = React.useState(1)

  const { data, isLoading, error } = useCommunityPosts(region, utilityType, page)

  if (isLoading) {
    return (
      <div data-testid="post-list-loading" className="space-y-4">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} variant="rectangular" height={120} />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div data-testid="post-list-error" className="rounded-xl border bg-white p-6 text-gray-500">
        Unable to load community posts.
      </div>
    )
  }

  if (!data?.posts?.length) {
    return (
      <div data-testid="post-list-empty" className="rounded-xl border bg-white p-8 text-center">
        <p className="text-sm text-gray-500">No posts yet. Be the first to share!</p>
      </div>
    )
  }

  return (
    <div data-testid="post-list">
      <div className="space-y-4">
        {data.posts.map((post) => (
          <PostCard
            key={post.id}
            post={post}
            isAuthor={post.user_id === currentUserId}
            onEdit={onEditPost}
          />
        ))}
      </div>

      {/* Pagination */}
      {data.pages > 1 && (
        <div className="mt-6 flex items-center justify-center gap-4" data-testid="post-pagination">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="rounded-lg border px-4 py-2 text-sm disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-sm text-gray-500">
            Page {data.page} of {data.pages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
            disabled={page >= data.pages}
            className="rounded-lg border px-4 py-2 text-sm disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// PostCard
// ---------------------------------------------------------------------------

function PostCard({
  post,
  isAuthor,
  onEdit,
}: {
  post: CommunityPost
  isAuthor: boolean
  onEdit?: (post: CommunityPost) => void
}) {
  // Hidden post (flagged by reports)
  if (post.is_hidden && !isAuthor) {
    return (
      <div data-testid={`post-${post.id}-hidden`} className="rounded-xl border bg-gray-50 p-4">
        <p className="text-sm text-gray-400">[Content under review]</p>
      </div>
    )
  }

  // Author's pending moderation
  if (post.is_pending_moderation && isAuthor) {
    return (
      <div data-testid={`post-${post.id}-pending`} className="rounded-xl border border-warning-200 bg-warning-50 p-4">
        <div className="mb-2 text-xs font-medium text-warning-600">Your post is being reviewed</div>
        <h4 className="text-sm font-medium text-gray-800">{post.title}</h4>
        <p className="mt-1 text-sm text-gray-600 line-clamp-3">{post.body}</p>
      </div>
    )
  }

  // Hidden from author — show edit option
  if (post.is_hidden && isAuthor) {
    return (
      <div data-testid={`post-${post.id}-flagged`} className="rounded-xl border border-danger-200 bg-danger-50 p-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-medium text-danger-600">Post flagged — edit to resubmit</span>
          {onEdit && (
            <button
              onClick={() => onEdit(post)}
              className="text-xs font-medium text-primary-600 hover:underline"
              data-testid={`post-${post.id}-edit-btn`}
            >
              Edit & Resubmit
            </button>
          )}
        </div>
        <h4 className="text-sm font-medium text-gray-800">{post.title}</h4>
        <p className="mt-1 text-sm text-gray-600 line-clamp-3">{post.body}</p>
      </div>
    )
  }

  return (
    <div data-testid={`post-${post.id}`} className="rounded-xl border bg-white p-4">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
              {POST_TYPE_LABELS[post.post_type] || post.post_type}
            </span>
            <span className="text-xs text-gray-400">{timeAgo(post.created_at)}</span>
          </div>
          <h4 className="mt-1 text-sm font-medium text-gray-800">{post.title}</h4>
          <p className="mt-1 text-sm text-gray-600 line-clamp-3">{post.body}</p>

          {/* Rate info for rate_report type */}
          {post.post_type === 'rate_report' && post.rate_per_unit != null && (
            <p className="mt-2 text-xs text-gray-500">
              Rate: ${post.rate_per_unit}/{post.rate_unit || 'kWh'}
              {post.supplier_name && ` — ${post.supplier_name}`}
            </p>
          )}
        </div>
      </div>

      <div className="mt-3 flex items-center gap-4">
        <VoteButton postId={post.id} count={post.upvote_count} />
        <ReportButton postId={post.id} />
      </div>
    </div>
  )
}
