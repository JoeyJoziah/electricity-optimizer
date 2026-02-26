import { Sidebar } from '@/components/layout/Sidebar'
import { SidebarProvider } from '@/lib/contexts/sidebar-context'

export default function AppLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <SidebarProvider>
      <div className="flex min-h-screen">
        <Sidebar />
        <main className="flex-1 lg:pl-64">{children}</main>
      </div>
    </SidebarProvider>
  )
}
