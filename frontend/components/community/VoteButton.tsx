'use client'

import React from 'react'
import { useToggleVote } from '@/lib/hooks/useCommunity'

interface VoteButtonProps {
  postId: string
  count: number
}

export function VoteButton({ postId, count }: VoteButtonProps) {
  const mutation = useToggleVote()
  const [optimisticCount, setOptimisticCount] = React.useState(count)
  const [voted, setVoted] = React.useState(false)

  // Sync with prop changes (e.g. after query refetch)
  React.useEffect(() => {
    setOptimisticCount(count)
  }, [count])

  function handleClick() {
    const newVoted = !voted
    // Capture the pre-click count for rollback (avoids stale closure over `count` prop)
    const prevCount = optimisticCount
    const prevVoted = voted

    setVoted(newVoted)
    setOptimisticCount((c) => (newVoted ? c + 1 : Math.max(0, c - 1)))

    mutation.mutate(postId, {
      onSuccess: (data) => {
        setVoted(data.voted)
        setOptimisticCount(data.upvote_count)
      },
      onError: () => {
        // Revert optimistic update to the values captured at click time
        setVoted(prevVoted)
        setOptimisticCount(prevCount)
      },
    })
  }

  return (
    <button
      onClick={handleClick}
      disabled={mutation.isPending}
      data-testid={`vote-btn-${postId}`}
      className={`flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
        voted
          ? 'bg-primary-100 text-primary-700'
          : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
      }`}
    >
      <span aria-hidden="true">{voted ? '\u25B2' : '\u25B3'}</span>
      <span data-testid={`vote-count-${postId}`}>{optimisticCount}</span>
    </button>
  )
}
