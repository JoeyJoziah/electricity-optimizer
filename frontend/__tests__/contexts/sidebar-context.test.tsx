import React from 'react'
import { renderHook, act } from '@testing-library/react'
import '@testing-library/jest-dom'
import { SidebarProvider, useSidebar } from '@/lib/contexts/sidebar-context'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <SidebarProvider>{children}</SidebarProvider>
  }
}

// ---------------------------------------------------------------------------
// Default context values (no provider)
// ---------------------------------------------------------------------------
describe('useSidebar — default values without provider', () => {
  it('returns isOpen: false without a provider (uses context default)', () => {
    // SidebarContext has a non-null default value, so this does NOT throw
    const { result } = renderHook(() => useSidebar())
    expect(result.current.isOpen).toBe(false)
  })

  it('toggle and close are no-ops without a provider', () => {
    const { result } = renderHook(() => useSidebar())
    // Should not throw
    expect(() => result.current.toggle()).not.toThrow()
    expect(() => result.current.close()).not.toThrow()
  })
})

// ---------------------------------------------------------------------------
// Initial state
// ---------------------------------------------------------------------------
describe('SidebarProvider — initial state', () => {
  it('starts with isOpen false', () => {
    const wrapper = createWrapper()
    const { result } = renderHook(() => useSidebar(), { wrapper })

    expect(result.current.isOpen).toBe(false)
  })

  it('exposes toggle and close methods', () => {
    const wrapper = createWrapper()
    const { result } = renderHook(() => useSidebar(), { wrapper })

    expect(typeof result.current.toggle).toBe('function')
    expect(typeof result.current.close).toBe('function')
  })

  it('renders children', () => {
    const { getByText } = renderWithProvider(<span>child content</span>)
    expect(getByText('child content')).not.toBeNull()
  })
})

// Utility render helper for component-based tests
function renderWithProvider(children: React.ReactNode) {
  const { getByText, queryByText } = require('@testing-library/react').render(
    <SidebarProvider>{children}</SidebarProvider>
  )
  return { getByText, queryByText }
}

// ---------------------------------------------------------------------------
// toggle()
// ---------------------------------------------------------------------------
describe('toggle()', () => {
  it('opens the sidebar when it is closed', () => {
    const wrapper = createWrapper()
    const { result } = renderHook(() => useSidebar(), { wrapper })

    expect(result.current.isOpen).toBe(false)

    act(() => {
      result.current.toggle()
    })

    expect(result.current.isOpen).toBe(true)
  })

  it('closes the sidebar when it is open', () => {
    const wrapper = createWrapper()
    const { result } = renderHook(() => useSidebar(), { wrapper })

    act(() => {
      result.current.toggle()
    })
    expect(result.current.isOpen).toBe(true)

    act(() => {
      result.current.toggle()
    })
    expect(result.current.isOpen).toBe(false)
  })

  it('alternates state on each call', () => {
    const wrapper = createWrapper()
    const { result } = renderHook(() => useSidebar(), { wrapper })

    const states: boolean[] = []

    for (let i = 0; i < 6; i++) {
      act(() => {
        result.current.toggle()
      })
      states.push(result.current.isOpen)
    }

    expect(states).toEqual([true, false, true, false, true, false])
  })
})

// ---------------------------------------------------------------------------
// close()
// ---------------------------------------------------------------------------
describe('close()', () => {
  it('closes an open sidebar', () => {
    const wrapper = createWrapper()
    const { result } = renderHook(() => useSidebar(), { wrapper })

    act(() => {
      result.current.toggle()
    })
    expect(result.current.isOpen).toBe(true)

    act(() => {
      result.current.close()
    })
    expect(result.current.isOpen).toBe(false)
  })

  it('is a no-op when sidebar is already closed', () => {
    const wrapper = createWrapper()
    const { result } = renderHook(() => useSidebar(), { wrapper })

    expect(result.current.isOpen).toBe(false)

    act(() => {
      result.current.close()
    })

    expect(result.current.isOpen).toBe(false)
  })

  it('can be called multiple times without error', () => {
    const wrapper = createWrapper()
    const { result } = renderHook(() => useSidebar(), { wrapper })

    act(() => {
      result.current.toggle()
    })

    act(() => {
      result.current.close()
      result.current.close()
      result.current.close()
    })

    expect(result.current.isOpen).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// Escape key behaviour
// ---------------------------------------------------------------------------
describe('Escape key handling', () => {
  it('closes the sidebar when Escape is pressed while open', () => {
    const wrapper = createWrapper()
    const { result } = renderHook(() => useSidebar(), { wrapper })

    act(() => {
      result.current.toggle()
    })
    expect(result.current.isOpen).toBe(true)

    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    })

    expect(result.current.isOpen).toBe(false)
  })

  it('does not attach Escape listener when sidebar is closed', () => {
    const addEventSpy = jest.spyOn(document, 'addEventListener')

    const wrapper = createWrapper()
    renderHook(() => useSidebar(), { wrapper })

    // Sidebar starts closed — no listener should be attached yet
    const keydownCalls = addEventSpy.mock.calls.filter(
      ([event]) => event === 'keydown'
    )
    expect(keydownCalls).toHaveLength(0)

    addEventSpy.mockRestore()
  })

  it('ignores non-Escape keydown events', () => {
    const wrapper = createWrapper()
    const { result } = renderHook(() => useSidebar(), { wrapper })

    act(() => {
      result.current.toggle()
    })
    expect(result.current.isOpen).toBe(true)

    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))
    })

    expect(result.current.isOpen).toBe(true)
  })

  it('removes the Escape listener when sidebar closes', () => {
    const removeEventSpy = jest.spyOn(document, 'removeEventListener')

    const wrapper = createWrapper()
    const { result } = renderHook(() => useSidebar(), { wrapper })

    // Open the sidebar (this registers the listener)
    act(() => {
      result.current.toggle()
    })

    // Close via Escape (triggers cleanup)
    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    })

    expect(result.current.isOpen).toBe(false)
    const removedKeydownListeners = removeEventSpy.mock.calls.filter(
      ([event]) => event === 'keydown'
    )
    expect(removedKeydownListeners.length).toBeGreaterThan(0)

    removeEventSpy.mockRestore()
  })

  it('removes the Escape listener on unmount', () => {
    const removeEventSpy = jest.spyOn(document, 'removeEventListener')

    const wrapper = createWrapper()
    const { result, unmount } = renderHook(() => useSidebar(), { wrapper })

    act(() => {
      result.current.toggle()
    })

    unmount()

    const removedKeydownListeners = removeEventSpy.mock.calls.filter(
      ([event]) => event === 'keydown'
    )
    expect(removedKeydownListeners.length).toBeGreaterThan(0)

    removeEventSpy.mockRestore()
  })
})

// ---------------------------------------------------------------------------
// Body scroll lock
// ---------------------------------------------------------------------------
describe('body scroll lock', () => {
  let originalInnerWidth: number

  beforeEach(() => {
    originalInnerWidth = window.innerWidth
  })

  afterEach(() => {
    // Restore body overflow and viewport width between tests
    document.body.style.overflow = ''
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: originalInnerWidth,
    })
  })

  /**
   * Helper to simulate a mobile viewport (below the lg breakpoint of 1024px).
   */
  function setMobileViewport() {
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: 375,
    })
  }

  /**
   * Helper to simulate a desktop viewport (at or above the lg breakpoint).
   */
  function setDesktopViewport() {
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: 1280,
    })
  }

  it('sets body overflow to "hidden" when sidebar opens on mobile', () => {
    setMobileViewport()
    const wrapper = createWrapper()
    const { result } = renderHook(() => useSidebar(), { wrapper })

    act(() => {
      result.current.toggle()
    })

    expect(document.body.style.overflow).toBe('hidden')
  })

  it('does NOT set body overflow to "hidden" when sidebar opens on desktop', () => {
    setDesktopViewport()
    const wrapper = createWrapper()
    const { result } = renderHook(() => useSidebar(), { wrapper })

    act(() => {
      result.current.toggle()
    })

    expect(document.body.style.overflow).not.toBe('hidden')
  })

  it('restores body overflow to "" when sidebar closes on mobile', () => {
    setMobileViewport()
    const wrapper = createWrapper()
    const { result } = renderHook(() => useSidebar(), { wrapper })

    act(() => {
      result.current.toggle()
    })
    expect(document.body.style.overflow).toBe('hidden')

    act(() => {
      result.current.close()
    })
    expect(document.body.style.overflow).toBe('')
  })

  it('does not lock body scroll when sidebar is initially closed', () => {
    renderHook(() => useSidebar(), { wrapper: createWrapper() })

    expect(document.body.style.overflow).not.toBe('hidden')
  })

  it('restores body overflow on unmount when sidebar was open on mobile', () => {
    setMobileViewport()
    const wrapper = createWrapper()
    const { result, unmount } = renderHook(() => useSidebar(), { wrapper })

    act(() => {
      result.current.toggle()
    })
    expect(document.body.style.overflow).toBe('hidden')

    unmount()

    expect(document.body.style.overflow).toBe('')
  })
})
