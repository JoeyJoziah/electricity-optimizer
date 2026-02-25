import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'

const mockSaveMutate = jest.fn()
const mockCreateMutate = jest.fn()

jest.mock('@/lib/hooks/useDiagrams', () => {
  // Access the outer-scope mock fns via the jest global trick:
  // jest.fn() calls inside the factory are fine, but we need references
  // from tests. We re-import them below after mock setup.
  return {
    useDiagramList: jest.fn(),
    useDiagram: jest.fn(),
    useSaveDiagram: jest.fn(),
    useCreateDiagram: jest.fn(),
  }
})

jest.mock('@/components/dev/DiagramList', () => ({
  DiagramList: (props: any) => (
    <div data-testid="diagram-list">
      <button data-testid="select-diagram" onClick={() => props.onSelect('test')}>
        Select
      </button>
      <button data-testid="create-diagram" onClick={props.onCreateClick}>
        Create
      </button>
    </div>
  ),
}))

jest.mock('@/components/dev/DiagramEditor', () => ({
  DiagramEditor: (props: any) => (
    <div data-testid="diagram-editor" data-name={props.name}>
      <button data-testid="save-diagram" onClick={() => props.onSave({ elements: [] })}>
        Save
      </button>
    </div>
  ),
}))

import ArchitecturePage from '@/app/(dev)/architecture/page'
import {
  useDiagramList,
  useDiagram,
  useSaveDiagram,
  useCreateDiagram,
} from '@/lib/hooks/useDiagrams'

const mockedUseDiagramList = useDiagramList as jest.Mock
const mockedUseDiagram = useDiagram as jest.Mock
const mockedUseSaveDiagram = useSaveDiagram as jest.Mock
const mockedUseCreateDiagram = useCreateDiagram as jest.Mock

function setupDefaultMocks() {
  mockedUseDiagramList.mockReturnValue({
    data: [
      { name: 'system-overview', updatedAt: '2026-02-20T00:00:00Z' },
      { name: 'data-flow', updatedAt: '2026-02-21T00:00:00Z' },
    ],
    isLoading: false,
  })
  mockedUseDiagram.mockReturnValue({
    data: { name: 'system-overview', data: { elements: [] } },
    isLoading: false,
  })
  mockedUseSaveDiagram.mockReturnValue({
    mutate: mockSaveMutate,
    isPending: false,
  })
  mockedUseCreateDiagram.mockReturnValue({
    mutate: mockCreateMutate,
    isPending: false,
  })
}

describe('ArchitecturePage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    setupDefaultMocks()
  })

  it('renders both DiagramList and DiagramEditor', () => {
    render(<ArchitecturePage />)

    expect(screen.getByTestId('diagram-list')).toBeInTheDocument()
    expect(screen.getByTestId('diagram-editor')).toBeInTheDocument()
  })

  it('passes selected diagram name to DiagramEditor when selected', async () => {
    render(<ArchitecturePage />)

    fireEvent.click(screen.getByTestId('select-diagram'))

    await waitFor(() => {
      const editor = screen.getByTestId('diagram-editor')
      expect(editor).toHaveAttribute('data-name', 'test')
    })
  })

  it('calls save mutation when editor triggers save', async () => {
    render(<ArchitecturePage />)

    // First select a diagram so that `selected` is non-null
    fireEvent.click(screen.getByTestId('select-diagram'))

    await waitFor(() => {
      expect(screen.getByTestId('diagram-editor')).toHaveAttribute('data-name', 'test')
    })

    fireEvent.click(screen.getByTestId('save-diagram'))

    expect(mockSaveMutate).toHaveBeenCalledTimes(1)
    expect(mockSaveMutate).toHaveBeenCalledWith({
      name: 'test',
      data: { elements: [] },
    })
  })

  it('has a 256px sidebar width for the list panel', () => {
    render(<ArchitecturePage />)

    // The list panel uses Tailwind class w-64 (256px)
    const listPanel = screen.getByTestId('diagram-list').parentElement as HTMLElement
    expect(listPanel.className).toContain('w-64')
  })
})
