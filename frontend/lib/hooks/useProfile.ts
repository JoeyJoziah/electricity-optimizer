'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getUserProfile, updateUserProfile, UpdateProfileData } from '@/lib/api/profile'
import { useSettingsStore } from '@/lib/store/settings'

/**
 * Hook for fetching and syncing the user profile from the backend.
 *
 * On successful fetch, syncs the backend region into the Zustand settings store
 * so that all hooks/components consuming `useSettingsStore` see the correct region.
 */
export function useProfile() {
  return useQuery({
    queryKey: ['user-profile'],
    queryFn: async () => {
      const profile = await getUserProfile()
      // Sync region from backend → Zustand store
      if (profile.region) {
        const store = useSettingsStore.getState()
        if (store.region !== profile.region) {
          store.setRegion(profile.region)
        }
      }
      return profile
    },
    staleTime: 60000,
  })
}

/**
 * Hook for updating the user profile on the backend.
 */
export function useUpdateProfile() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: UpdateProfileData) => updateUserProfile(data),
    onSuccess: (profile) => {
      queryClient.setQueryData(['user-profile'], profile)
      // Sync region to Zustand store
      if (profile.region) {
        useSettingsStore.getState().setRegion(profile.region)
      }
    },
  })
}
