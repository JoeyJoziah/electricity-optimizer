import { render, screen } from '@testing-library/react'
import { FTCDisclosure } from '@/components/affiliate/FTCDisclosure'
import '@testing-library/jest-dom'

describe('FTCDisclosure', () => {
  it('renders inline variant by default', () => {
    render(<FTCDisclosure />)
    const note = screen.getByRole('note', { name: 'Affiliate disclosure' })
    expect(note).toBeInTheDocument()
    expect(note.tagName).toBe('P')
    expect(note).toHaveTextContent(/may earn a commission/)
  })

  it('renders banner variant with stronger emphasis', () => {
    render(<FTCDisclosure variant="banner" />)
    const note = screen.getByRole('note', { name: 'Affiliate disclosure' })
    expect(note).toBeInTheDocument()
    expect(note.tagName).toBe('DIV')
    expect(screen.getByText('Disclosure:')).toBeInTheDocument()
  })

  it('states rates are not affected (inline)', () => {
    render(<FTCDisclosure />)
    expect(screen.getByText(/rankings are not affected/)).toBeInTheDocument()
  })

  it('states supplier ordering not influenced (banner)', () => {
    render(<FTCDisclosure variant="banner" />)
    expect(
      screen.getByText(/does not affect our rate comparisons/)
    ).toBeInTheDocument()
  })

  it('has accessible aria-label', () => {
    render(<FTCDisclosure />)
    expect(
      screen.getByRole('note', { name: 'Affiliate disclosure' })
    ).toBeInTheDocument()
  })
})
