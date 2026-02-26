import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConnectionMethodPicker } from '@/components/connections/ConnectionMethodPicker'
import '@testing-library/jest-dom'

// Mock cn utility
jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

// Mock lucide-react icons
jest.mock('lucide-react', () => ({
  KeyRound: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-key" {...props} />,
  Mail: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-mail" {...props} />,
  Upload: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-upload" {...props} />,
  ArrowRight: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-arrow" {...props} />,
}))

describe('ConnectionMethodPicker', () => {
  const defaultProps = {
    onSelectDirect: jest.fn(),
    onSelectEmail: jest.fn(),
    onSelectUpload: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders all three connection method options', () => {
    render(<ConnectionMethodPicker {...defaultProps} />)

    expect(screen.getByText('Utility Account')).toBeInTheDocument()
    expect(screen.getByText('Email Inbox')).toBeInTheDocument()
    expect(screen.getByText('Upload Bills')).toBeInTheDocument()
  })

  it('renders descriptions for each method', () => {
    render(<ConnectionMethodPicker {...defaultProps} />)

    expect(
      screen.getByText(/connect directly to your utility provider/i)
    ).toBeInTheDocument()
    expect(
      screen.getByText(/scan your email for utility bills/i)
    ).toBeInTheDocument()
    expect(
      screen.getByText(/upload pdf or image bills/i)
    ).toBeInTheDocument()
  })

  it('renders connect text for each method button', () => {
    render(<ConnectionMethodPicker {...defaultProps} />)

    const connectTexts = screen.getAllByText('Connect')
    expect(connectTexts).toHaveLength(3)
  })

  it('calls onSelectDirect when Utility Account is clicked', async () => {
    const user = userEvent.setup()
    render(<ConnectionMethodPicker {...defaultProps} />)

    await user.click(screen.getByText('Utility Account'))

    expect(defaultProps.onSelectDirect).toHaveBeenCalledTimes(1)
  })

  it('calls onSelectEmail when Email Inbox is clicked', async () => {
    const user = userEvent.setup()
    render(<ConnectionMethodPicker {...defaultProps} />)

    await user.click(screen.getByText('Email Inbox'))

    expect(defaultProps.onSelectEmail).toHaveBeenCalledTimes(1)
  })

  it('calls onSelectUpload when Upload Bills is clicked', async () => {
    const user = userEvent.setup()
    render(<ConnectionMethodPicker {...defaultProps} />)

    await user.click(screen.getByText('Upload Bills'))

    expect(defaultProps.onSelectUpload).toHaveBeenCalledTimes(1)
  })

  it('renders three buttons accessible by role', () => {
    render(<ConnectionMethodPicker {...defaultProps} />)

    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(3)
  })

  it('has keyboard-accessible buttons with focus styles', () => {
    render(<ConnectionMethodPicker {...defaultProps} />)

    const buttons = screen.getAllByRole('button')
    buttons.forEach((button) => {
      expect(button.className).toContain('focus:outline-none')
    })
  })
})
