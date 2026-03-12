import { apiClient } from './client'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CommunityPost {
  id: string
  user_id: string
  region: string
  utility_type: string
  post_type: string
  title: string
  body: string
  rate_per_unit: number | null
  rate_unit: string | null
  supplier_name: string | null
  is_hidden: boolean
  is_pending_moderation: boolean
  hidden_reason: string | null
  upvote_count: number
  created_at: string
  updated_at: string
}

export interface PostsResponse {
  posts: CommunityPost[]
  total: number
  page: number
  per_page: number
  pages: number
}

export interface CreatePostPayload {
  title: string
  body: string
  utility_type: string
  region: string
  post_type: string
  rate_per_unit?: number | null
  rate_unit?: string | null
  supplier_name?: string | null
}

export interface VoteResponse {
  voted: boolean
  upvote_count: number
}

export interface CommunityStatsResponse {
  user_count: number
  post_count: number
  avg_savings_pct: number | null
  top_tip: CommunityPost | null
  since: string | null
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function fetchPosts(
  region: string,
  utilityType: string,
  page = 1,
  perPage = 20,
): Promise<PostsResponse> {
  return apiClient.get<PostsResponse>('/community/posts', {
    region,
    utility_type: utilityType,
    page,
    per_page: perPage,
  })
}

export async function createPost(data: CreatePostPayload): Promise<CommunityPost> {
  return apiClient.post<CommunityPost>('/community/posts', data)
}

export async function editPost(
  postId: string,
  data: { title?: string; body?: string; supplier_name?: string },
): Promise<CommunityPost> {
  return apiClient.put<CommunityPost>(`/community/posts/${postId}`, data)
}

export async function toggleVote(postId: string): Promise<VoteResponse> {
  return apiClient.post<VoteResponse>(`/community/posts/${postId}/vote`, {})
}

export async function reportPost(postId: string, reason?: string): Promise<{ status: string }> {
  return apiClient.post<{ status: string }>(`/community/posts/${postId}/report`, { reason })
}

export async function fetchCommunityStats(region: string): Promise<CommunityStatsResponse> {
  return apiClient.get<CommunityStatsResponse>('/community/stats', { region })
}
