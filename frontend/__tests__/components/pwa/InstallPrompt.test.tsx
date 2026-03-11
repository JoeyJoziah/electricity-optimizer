import { render, screen, fireEvent, act } from '@testing-library/react'
import { InstallPrompt } from '@/components/pwa/InstallPrompt'

// Storage mock helpers
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { store = {} },
  }
})()

Object.defineProperty(window, 'localStorage', { value: localStorageMock })

describe('InstallPrompt', () => {
  beforeEach(() => {
    localStorageMock.clear()
  })

  it('does not render on first visit', () => {
    render(<InstallPrompt />)
    expect(screen.queryByTestId('install-prompt')).toBeNull()
  })

  it('does not render on second visit without beforeinstallprompt', () => {
    localStorageMock.setItem('rateshift_visit_count', '1')
    render(<InstallPrompt />)
    expect(screen.queryByTestId('install-prompt')).toBeNull()
  })

  it('renders after 2nd visit when beforeinstallprompt fires', async () => {
    localStorageMock.setItem('rateshift_visit_count', '1')

    render(<InstallPrompt />)

    // Simulate the browser event
    await act(async () => {
      const event = new Event('beforeinstallprompt', { cancelable: true })
      window.dispatchEvent(event)
    })

    expect(screen.getByTestId('install-prompt')).toBeTruthy()
    expect(screen.getByText('Install RateShift')).toBeTruthy()
  })

  it('dismisses and persists dismissal', async () => {
    localStorageMock.setItem('rateshift_visit_count', '1')

    render(<InstallPrompt />)

    await act(async () => {
      const event = new Event('beforeinstallprompt', { cancelable: true })
      window.dispatchEvent(event)
    })

    expect(screen.getByTestId('install-prompt')).toBeTruthy()

    fireEvent.click(screen.getByLabelText('Dismiss install prompt'))

    expect(screen.queryByTestId('install-prompt')).toBeNull()
    expect(localStorageMock.getItem('rateshift_install_dismissed')).toBe('true')
  })

  it('does not render when previously dismissed', () => {
    localStorageMock.setItem('rateshift_visit_count', '5')
    localStorageMock.setItem('rateshift_install_dismissed', 'true')

    render(<InstallPrompt />)
    expect(screen.queryByTestId('install-prompt')).toBeNull()
  })

  it('increments visit counter', () => {
    localStorageMock.setItem('rateshift_visit_count', '3')
    render(<InstallPrompt />)
    expect(localStorageMock.getItem('rateshift_visit_count')).toBe('4')
  })
})
