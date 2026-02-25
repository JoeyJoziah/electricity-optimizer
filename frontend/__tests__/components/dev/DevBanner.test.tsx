import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'
import { DevBanner } from '@/components/dev/DevBanner'

jest.mock('@/lib/utils/devGate', () => ({
  isDevMode: jest.fn(),
}))

jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

import { isDevMode } from '@/lib/utils/devGate'

const mockedIsDevMode = isDevMode as jest.MockedFunction<typeof isDevMode>

describe('DevBanner', () => {
  it('renders "Development Mode" text when isDevMode returns true', () => {
    mockedIsDevMode.mockReturnValue(true)

    render(<DevBanner />)

    expect(screen.getByText('Development Mode')).toBeInTheDocument()
  })

  it('renders nothing when isDevMode returns false', () => {
    mockedIsDevMode.mockReturnValue(false)

    const { container } = render(<DevBanner />)

    expect(container.innerHTML).toBe('')
    expect(screen.queryByText('Development Mode')).not.toBeInTheDocument()
  })
})
