import { Skeleton } from '@/components/ui/skeleton'

export default function BetaSignupLoading() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 p-4">
      <div className="max-w-2xl w-full rounded-xl border border-gray-200 bg-white p-8 space-y-6">
        {/* Header */}
        <div className="text-center space-y-3">
          <Skeleton variant="circular" width={64} height={64} className="mx-auto" />
          <Skeleton variant="text" className="mx-auto h-8 w-48" />
          <Skeleton variant="text" className="mx-auto h-4 w-80" />
        </div>
        {/* Form fields */}
        <div className="space-y-4">
          <Skeleton variant="text" className="h-5 w-40" />
          <Skeleton variant="rectangular" className="h-10 w-full" />
          <Skeleton variant="rectangular" className="h-10 w-full" />
          <Skeleton variant="rectangular" className="h-10 w-full" />
        </div>
        <div className="space-y-4">
          <Skeleton variant="text" className="h-5 w-48" />
          <Skeleton variant="rectangular" className="h-10 w-full" />
          <Skeleton variant="rectangular" className="h-10 w-full" />
          <Skeleton variant="rectangular" className="h-10 w-full" />
        </div>
        <Skeleton variant="rectangular" className="h-12 w-full" />
      </div>
    </div>
  )
}
