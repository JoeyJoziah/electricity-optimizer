import React from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'

/**
 * Renders the Today's Schedule section.
 * Currently shows an empty state prompting the user to configure appliances.
 */
export function DashboardSchedule() {
  return (
    <Card className="mt-6">
      <CardHeader>
        <CardTitle>Today&apos;s Schedule</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex h-32 items-center justify-center text-gray-400">
          <p>No optimization schedule set. Configure appliances in Settings to get started.</p>
        </div>
      </CardContent>
    </Card>
  )
}
