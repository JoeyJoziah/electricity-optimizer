'use client'

import { createContext, useContext, useState, useCallback, useEffect } from 'react'

interface SidebarContextValue {
  isOpen: boolean
  toggle: () => void
  close: () => void
}

const SidebarContext = createContext<SidebarContextValue>({
  isOpen: false,
  toggle: () => {},
  close: () => {},
})

/**
 * Tailwind `lg` breakpoint in pixels. The mobile sidebar overlay is only
 * rendered below this width (`lg:hidden`), so the body-scroll lock should
 * only apply on viewports narrower than this value.
 */
const LG_BREAKPOINT = 1024

export function SidebarProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setIsOpen] = useState(false)
  const toggle = useCallback(() => setIsOpen((v) => !v), [])
  const close = useCallback(() => setIsOpen(false), [])

  // Close sidebar on Escape key
  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        close()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, close])

  // Prevent body scroll when mobile sidebar overlay is open.
  // Only apply on viewports below the `lg` breakpoint where the
  // overlay backdrop is actually visible. On desktop (>=1024px) the
  // sidebar is a fixed column and should never block page scrolling.
  useEffect(() => {
    const isMobile =
      typeof window !== 'undefined' && window.innerWidth < LG_BREAKPOINT

    if (isOpen && isMobile) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [isOpen])

  return (
    <SidebarContext.Provider value={{ isOpen, toggle, close }}>
      {children}
    </SidebarContext.Provider>
  )
}

export function useSidebar() {
  return useContext(SidebarContext)
}
