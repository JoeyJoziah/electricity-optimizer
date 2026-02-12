import { Sidebar } from '@/components/layout/Sidebar'

export default function AppLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 lg:pl-64">{children}</main>
    </div>
  )
}
