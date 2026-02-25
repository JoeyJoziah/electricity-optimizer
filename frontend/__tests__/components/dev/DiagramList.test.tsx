import { render, screen, fireEvent } from '@testing-library/react'
import React from 'react'
import '@testing-library/jest-dom'
import type { DiagramEntry } from '@/lib/hooks/useDiagrams'

jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

jest.mock('lucide-react', () => ({
  Plus: (props: any) => <svg data-testid="plus-icon" {...props} />,
  FileText: (props: any) => <svg data-testid="file-icon" {...props} />,
  Loader2: (props: any) => <svg data-testid="loader-icon" {...props} />,
}))

import { DiagramList } from '@/components/dev/DiagramList'

const mockDiagrams: DiagramEntry[] = [
  { name: 'architecture', updatedAt: '2026-02-24T10:00:00Z' },
  { name: 'data-flow', updatedAt: '2026-02-24T11:00:00Z' },
  { name: 'deployment-pipeline', updatedAt: '2026-02-24T12:00:00Z' },
]

describe('DiagramList', () => {
  const defaultProps = {
    diagrams: mockDiagrams,
    isLoading: false,
    selected: null as string | null,
    onSelect: jest.fn(),
    onCreateClick: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('shows loading skeletons when isLoading is true', () => {
    render(<DiagramList {...defaultProps} isLoading={true} />)

    expect(screen.getByTestId('diagram-list-loading')).toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('renders "No diagrams yet" when list is empty', () => {
    render(<DiagramList {...defaultProps} diagrams={[]} />)

    expect(screen.getByText('No diagrams yet')).toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('renders list of diagram names', () => {
    render(<DiagramList {...defaultProps} />)

    expect(screen.getByRole('list')).toBeInTheDocument()
    expect(screen.getByText('architecture')).toBeInTheDocument()
    expect(screen.getByText('data-flow')).toBeInTheDocument()
    expect(screen.getByText('deployment-pipeline')).toBeInTheDocument()
  })

  it('highlights selected diagram', () => {
    render(<DiagramList {...defaultProps} selected="data-flow" />)

    const selectedButton = screen.getByText('data-flow').closest('button')
    expect(selectedButton).toBeInTheDocument()
    // When selected, cn produces a class string containing the selected style
    expect(selectedButton?.className).toContain('bg-primary-100')
    expect(selectedButton?.className).toContain('font-medium')

    // Non-selected buttons should not have the selected style
    const otherButton = screen.getByText('architecture').closest('button')
    expect(otherButton?.className).not.toContain('bg-primary-100')
  })

  it('calls onSelect when clicking a diagram', () => {
    const onSelect = jest.fn()

    render(<DiagramList {...defaultProps} onSelect={onSelect} />)

    fireEvent.click(screen.getByText('data-flow'))

    expect(onSelect).toHaveBeenCalledTimes(1)
    expect(onSelect).toHaveBeenCalledWith('data-flow')
  })

  it('calls onCreateClick when clicking create button', () => {
    const onCreateClick = jest.fn()

    render(<DiagramList {...defaultProps} onCreateClick={onCreateClick} />)

    const createButton = screen.getByLabelText('Create diagram')
    fireEvent.click(createButton)

    expect(onCreateClick).toHaveBeenCalledTimes(1)
  })

  it('shows diagram names truncated in buttons', () => {
    render(<DiagramList {...defaultProps} />)

    // Each diagram name is wrapped in a <span> with className containing 'truncate'
    const nameSpans = mockDiagrams.map((d) => screen.getByText(d.name))
    nameSpans.forEach((span) => {
      expect(span.className).toContain('truncate')
    })
  })
})
