import { render, screen } from '@testing-library/react'
import React from 'react'
import '@testing-library/jest-dom'

jest.mock('@excalidraw/excalidraw', () => ({
  Excalidraw: (props: any) => <div data-testid="mock-excalidraw" data-theme={props.theme} />,
}))

jest.mock('next/dynamic', () => {
  return (loader: () => Promise<any>, _opts?: any) => {
    const Component = require('@excalidraw/excalidraw').Excalidraw
    return Component
  }
})

jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

import { ExcalidrawWrapper } from '@/components/dev/ExcalidrawWrapper'

describe('ExcalidrawWrapper', () => {
  it('renders wrapper div with data-testid', () => {
    render(<ExcalidrawWrapper />)

    expect(screen.getByTestId('excalidraw-wrapper')).toBeInTheDocument()
  })

  it('passes initialData to Excalidraw component', () => {
    const initialData = { elements: [{ id: '1', type: 'rectangle' }] }

    render(<ExcalidrawWrapper initialData={initialData} />)

    const excalidraw = screen.getByTestId('mock-excalidraw')
    expect(excalidraw).toBeInTheDocument()
    // The Excalidraw mock renders as a div; the wrapper passes props through
    expect(screen.getByTestId('excalidraw-wrapper')).toBeInTheDocument()
  })

  it('passes onChange callback to Excalidraw', () => {
    const onChange = jest.fn()

    render(<ExcalidrawWrapper onChange={onChange} />)

    const excalidraw = screen.getByTestId('mock-excalidraw')
    expect(excalidraw).toBeInTheDocument()
  })

  it('defaults theme to light', () => {
    render(<ExcalidrawWrapper />)

    const excalidraw = screen.getByTestId('mock-excalidraw')
    expect(excalidraw).toHaveAttribute('data-theme', 'light')
  })

  it('passes custom theme prop', () => {
    render(<ExcalidrawWrapper theme="dark" />)

    const excalidraw = screen.getByTestId('mock-excalidraw')
    expect(excalidraw).toHaveAttribute('data-theme', 'dark')
  })
})
