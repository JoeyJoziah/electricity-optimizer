import { render, screen, fireEvent, act } from '@testing-library/react'
import React from 'react'
import '@testing-library/jest-dom'

jest.mock('@/components/dev/ExcalidrawWrapper', () => ({
  ExcalidrawWrapper: ({ onChange, initialData }: any) => (
    <div data-testid="mock-excalidraw">
      <button
        data-testid="trigger-change"
        onClick={() =>
          onChange?.([{ id: '1' }], {
            gridSize: null,
            viewBackgroundColor: '#fff',
          })
        }
      >
        change
      </button>
    </div>
  ),
}))

jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

jest.mock('lucide-react', () => ({
  Save: (props: any) => <svg data-testid="save-icon" {...props} />,
  Check: (props: any) => <svg data-testid="check-icon" {...props} />,
  Loader2: (props: any) => <svg data-testid="loader-icon" {...props} />,
}))

import { DiagramEditor } from '@/components/dev/DiagramEditor'

describe('DiagramEditor', () => {
  const defaultProps = {
    name: 'architecture' as string | null,
    data: { type: 'excalidraw', version: 2, elements: [] } as Record<string, unknown> | undefined,
    isLoading: false,
    onSave: jest.fn(),
    isSaving: false,
  }

  beforeEach(() => {
    jest.clearAllMocks()
    jest.useFakeTimers()
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  it('shows placeholder when no diagram selected (name is null)', () => {
    render(<DiagramEditor {...defaultProps} name={null} />)

    expect(screen.getByText('Select a diagram or create a new one')).toBeInTheDocument()
    expect(screen.queryByTestId('mock-excalidraw')).not.toBeInTheDocument()
  })

  it('shows loading skeleton when isLoading is true', () => {
    render(<DiagramEditor {...defaultProps} isLoading={true} />)

    expect(screen.getByTestId('editor-loading')).toBeInTheDocument()
    expect(screen.queryByTestId('mock-excalidraw')).not.toBeInTheDocument()
  })

  it('renders diagram name in toolbar', () => {
    render(<DiagramEditor {...defaultProps} />)

    expect(screen.getByText('architecture')).toBeInTheDocument()
  })

  it('save button is disabled when no changes', () => {
    render(<DiagramEditor {...defaultProps} />)

    const saveButton = screen.getByLabelText('Save diagram')
    expect(saveButton).toBeDisabled()
  })

  it('clicking trigger-change enables save button and shows "Unsaved changes"', () => {
    render(<DiagramEditor {...defaultProps} />)

    // Save should be disabled initially
    expect(screen.getByLabelText('Save diagram')).toBeDisabled()
    expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument()

    // Trigger a change via the mock Excalidraw
    fireEvent.click(screen.getByTestId('trigger-change'))

    // Now save button should be enabled and "Unsaved changes" visible
    expect(screen.getByLabelText('Save diagram')).not.toBeDisabled()
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument()
  })

  it('clicking save calls onSave with diagram data', () => {
    const onSave = jest.fn()

    render(<DiagramEditor {...defaultProps} onSave={onSave} />)

    // Trigger a change first
    fireEvent.click(screen.getByTestId('trigger-change'))

    // Click save
    fireEvent.click(screen.getByLabelText('Save diagram'))

    expect(onSave).toHaveBeenCalledTimes(1)
    // handleChange builds the data object from elements + appState
    expect(onSave).toHaveBeenCalledWith({
      type: 'excalidraw',
      version: 2,
      source: 'electricity-optimizer',
      elements: [{ id: '1' }],
      appState: { gridSize: null, viewBackgroundColor: '#fff' },
      files: {},
    })

    // Save button should be disabled again after save
    expect(screen.getByLabelText('Save diagram')).toBeDisabled()
  })

  it('shows "Saved" indicator after save', () => {
    const onSave = jest.fn()

    render(<DiagramEditor {...defaultProps} onSave={onSave} />)

    // Trigger change, then save
    fireEvent.click(screen.getByTestId('trigger-change'))
    fireEvent.click(screen.getByLabelText('Save diagram'))

    // "Saved" indicator should appear
    expect(screen.getByTestId('save-indicator')).toBeInTheDocument()
    expect(screen.getByText('Saved')).toBeInTheDocument()
    expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument()

    // After 2 seconds, "Saved" indicator should disappear
    // Wrap in act() because advanceTimersByTime fires the setTimeout callback
    // which calls setShowSaved(false), triggering a React state update
    act(() => {
      jest.advanceTimersByTime(2000)
    })

    expect(screen.queryByTestId('save-indicator')).not.toBeInTheDocument()
    expect(screen.queryByText('Saved')).not.toBeInTheDocument()
  })

  it('Ctrl+S keyboard shortcut triggers save', () => {
    const onSave = jest.fn()

    render(<DiagramEditor {...defaultProps} onSave={onSave} />)

    // Trigger a change first so there is data to save
    fireEvent.click(screen.getByTestId('trigger-change'))

    // Press Ctrl+S
    fireEvent.keyDown(window, { key: 's', ctrlKey: true })

    expect(onSave).toHaveBeenCalledTimes(1)
    expect(onSave).toHaveBeenCalledWith({
      type: 'excalidraw',
      version: 2,
      source: 'electricity-optimizer',
      elements: [{ id: '1' }],
      appState: { gridSize: null, viewBackgroundColor: '#fff' },
      files: {},
    })
  })
})
