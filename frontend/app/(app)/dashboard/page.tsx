import { Suspense } from 'react'
import DashboardTabs from '@/components/dashboard/DashboardTabs'

export const metadata = { title: 'Dashboard | RateShift' }

export default function DashboardPage() {
  return (
    <Suspense>
      <DashboardTabs />
    </Suspense>
  )
}
