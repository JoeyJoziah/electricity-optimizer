'use client'

import React from 'react'
import { useReportPost } from '@/lib/hooks/useCommunity'

interface ReportButtonProps {
  postId: string
}

export function ReportButton({ postId }: ReportButtonProps) {
  const mutation = useReportPost()
  const [showConfirm, setShowConfirm] = React.useState(false)

  function handleReport() {
    mutation.mutate(
      { postId },
      {
        onSuccess: () => setShowConfirm(false),
      },
    )
  }

  if (showConfirm) {
    return (
      <div className="flex items-center gap-2" data-testid={`report-confirm-${postId}`}>
        <span className="text-xs text-gray-500">Report this post?</span>
        <button
          onClick={handleReport}
          disabled={mutation.isPending}
          className="text-xs font-medium text-red-600 hover:underline"
          data-testid={`report-yes-${postId}`}
        >
          Yes
        </button>
        <button
          onClick={() => setShowConfirm(false)}
          className="text-xs text-gray-500 hover:underline"
        >
          No
        </button>
      </div>
    )
  }

  return (
    <button
      onClick={() => setShowConfirm(true)}
      data-testid={`report-btn-${postId}`}
      className="text-xs text-gray-400 hover:text-red-500 transition-colors"
    >
      Report
    </button>
  )
}
