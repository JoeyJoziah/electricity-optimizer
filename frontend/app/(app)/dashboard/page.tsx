import { Suspense } from 'react'
import DashboardTabs from '@/components/dashboard/DashboardTabs'
import { ErrorBoundary } from '@/components/error-boundary'

export const metadata = { title: 'Dashboard | RateShift' }

export default function DashboardPage() {
  return (
    <ErrorBoundary>
      <Suspense>
        <DashboardTabs />
      </Suspense>
    </ErrorBoundary>
  )
}
