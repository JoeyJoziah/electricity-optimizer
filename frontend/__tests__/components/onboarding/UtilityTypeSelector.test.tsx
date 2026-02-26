import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { UtilityTypeSelector } from '@/components/onboarding/UtilityTypeSelector'
import '@testing-library/jest-dom'

describe('UtilityTypeSelector', () => {
  const onChange = jest.fn()

  beforeEach(() => {
    onChange.mockClear()
  })

  it('renders all utility type options', () => {
    render(<UtilityTypeSelector selected={['electricity']} onChange={onChange} />)

    expect(screen.getByText('Electricity')).toBeInTheDocument()
    expect(screen.getByText('Natural Gas')).toBeInTheDocument()
    expect(screen.getByText('Heating Oil')).toBeInTheDocument()
    expect(screen.getByText('Propane')).toBeInTheDocument()
    expect(screen.getByText('Community Solar')).toBeInTheDocument()
  })

  it('shows selected state for pre-selected types', () => {
    render(
      <UtilityTypeSelector
        selected={['electricity', 'natural_gas']}
        onChange={onChange}
      />
    )

    // Both should have check marks (the svg check element)
    const checks = document.querySelectorAll('svg path[d="M5 13l4 4L19 7"]')
    expect(checks.length).toBe(2)
  })

  it('calls onChange when toggling a type', async () => {
    const user = userEvent.setup()
    render(<UtilityTypeSelector selected={['electricity']} onChange={onChange} />)

    await user.click(screen.getByText('Natural Gas'))
    expect(onChange).toHaveBeenCalledWith(['electricity', 'natural_gas'])
  })

  it('removes a type when deselecting', async () => {
    const user = userEvent.setup()
    render(
      <UtilityTypeSelector
        selected={['electricity', 'natural_gas']}
        onChange={onChange}
      />
    )

    await user.click(screen.getByText('Natural Gas'))
    expect(onChange).toHaveBeenCalledWith(['electricity'])
  })

  it('prevents deselecting the last type', async () => {
    const user = userEvent.setup()
    render(<UtilityTypeSelector selected={['electricity']} onChange={onChange} />)

    await user.click(screen.getByText('Electricity'))
    expect(onChange).not.toHaveBeenCalled()
  })

  it('renders heading and description', () => {
    render(<UtilityTypeSelector selected={['electricity']} onChange={onChange} />)

    expect(screen.getByText('What utilities do you use?')).toBeInTheDocument()
    expect(screen.getByText(/Select all that apply/)).toBeInTheDocument()
  })
})
