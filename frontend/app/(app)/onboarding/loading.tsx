import { Skeleton } from '@/components/ui/skeleton'

export default function OnboardingLoading() {
  return (
    <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center px-4 py-12">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center space-y-3">
          <Skeleton variant="text" className="mx-auto h-8 w-52" />
          <Skeleton variant="text" className="mx-auto h-4 w-72" />
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-6 space-y-4">
          <Skeleton variant="text" className="h-5 w-28" />
          <Skeleton variant="rectangular" className="h-10 w-full" />
          <Skeleton variant="rectangular" className="h-10 w-full" />
        </div>
      </div>
    </div>
  )
}
