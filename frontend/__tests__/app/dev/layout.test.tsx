import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'

const mockNotFound = jest.fn()
jest.mock('next/navigation', () => ({
  notFound: () => {
    mockNotFound()
    throw new Error('NEXT_NOT_FOUND')
  },
}))

jest.mock('@/components/dev/DevBanner', () => ({
  DevBanner: () => <div data-testid="dev-banner">Dev Banner</div>,
}))

import DevLayout from '@/app/(dev)/layout'

const env = process.env as { NODE_ENV: string }
let originalNodeEnv: string

beforeEach(() => {
  originalNodeEnv = env.NODE_ENV
  jest.clearAllMocks()
})

afterEach(() => {
  env.NODE_ENV = originalNodeEnv
})

describe('DevLayout', () => {
  it('renders children and DevBanner in development mode', () => {
    env.NODE_ENV = 'development'

    render(
      <DevLayout>
        <p>child content</p>
      </DevLayout>
    )

    expect(screen.getByTestId('dev-banner')).toBeInTheDocument()
    expect(screen.getByText('child content')).toBeInTheDocument()
  })

  it('calls notFound() in production mode', () => {
    env.NODE_ENV = 'production'

    expect(() => {
      render(
        <DevLayout>
          <p>should not render</p>
        </DevLayout>
      )
    }).toThrow('NEXT_NOT_FOUND')

    // React may retry the render, so notFound can be called more than once
    expect(mockNotFound).toHaveBeenCalled()
  })

  it('calls notFound() in test mode (NODE_ENV=test is not development)', () => {
    env.NODE_ENV = 'test'

    expect(() => {
      render(
        <DevLayout>
          <p>should not render</p>
        </DevLayout>
      )
    }).toThrow('NEXT_NOT_FOUND')

    expect(mockNotFound).toHaveBeenCalled()
  })

  it('wraps content in a flex column layout', () => {
    env.NODE_ENV = 'development'

    const { container } = render(
      <DevLayout>
        <p>content</p>
      </DevLayout>
    )

    const wrapper = container.firstElementChild as HTMLElement
    expect(wrapper.tagName).toBe('DIV')
    expect(wrapper.className).toContain('flex')
    expect(wrapper.className).toContain('flex-col')
    expect(wrapper.className).toContain('min-h-screen')
  })
})
