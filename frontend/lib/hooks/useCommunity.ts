import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchPosts,
  createPost,
  toggleVote,
  reportPost,
  fetchCommunityStats,
} from '../api/community'
import type { CreatePostPayload } from '../api/community'

export function useCommunityPosts(region?: string, utilityType?: string, page = 1) {
  return useQuery({
    queryKey: ['community', 'posts', region, utilityType, page],
    queryFn: () => fetchPosts(region!, utilityType!, page),
    enabled: !!region && !!utilityType,
    staleTime: 1000 * 60 * 2, // 2 min
  })
}

export function useCreatePost() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreatePostPayload) => createPost(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['community', 'posts'] })
      qc.invalidateQueries({ queryKey: ['community', 'stats'] })
    },
  })
}

export function useToggleVote() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (postId: string) => toggleVote(postId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['community', 'posts'] })
    },
  })
}

export function useReportPost() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ postId, reason }: { postId: string; reason?: string }) =>
      reportPost(postId, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['community', 'posts'] })
    },
  })
}

export function useCommunityStats(region?: string) {
  return useQuery({
    queryKey: ['community', 'stats', region],
    queryFn: () => fetchCommunityStats(region!),
    enabled: !!region,
    staleTime: 1000 * 60 * 5,
  })
}
