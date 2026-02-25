import { notFound } from 'next/navigation'
import { DevBanner } from '@/components/dev/DevBanner'

export default function DevLayout({ children }: { children: React.ReactNode }) {
  if (process.env.NODE_ENV !== 'development') {
    notFound()
  }

  return (
    <div className="flex min-h-screen flex-col">
      <DevBanner />
      {children}
    </div>
  )
}
