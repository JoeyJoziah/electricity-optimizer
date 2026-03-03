import { render, fireEvent } from '@testing-library/react'
import { axe } from 'jest-axe'
import { Modal } from '@/components/ui/modal'
import '@testing-library/jest-dom'

jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

jest.mock('lucide-react', () => ({
  X: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="x-icon" {...props} />,
  Loader2: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="loader-icon" {...props} />,
}))

describe('Modal focus trap a11y', () => {
  it('has no accessibility violations when open', async () => {
    const { container } = render(
      <Modal open={true} onClose={jest.fn()} title="Confirm action">
        <p>Are you sure you want to proceed?</p>
      </Modal>
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('closes on Escape key press', () => {
    const onClose = jest.fn()
    render(
      <Modal open={true} onClose={onClose} title="Test modal">
        <button>Action</button>
      </Modal>
    )
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('has role="dialog" and aria-modal="true"', () => {
    const { container } = render(
      <Modal open={true} onClose={jest.fn()} title="Accessible modal" />
    )
    const dialog = container.querySelector('[role="dialog"]')
    expect(dialog).toBeInTheDocument()
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAttribute('aria-labelledby', 'modal-title')
  })

  it('modal title is linked via aria-labelledby', () => {
    const { container } = render(
      <Modal open={true} onClose={jest.fn()} title="Delete account" />
    )
    const title = container.querySelector('#modal-title')
    expect(title).toBeInTheDocument()
    expect(title).toHaveTextContent('Delete account')
  })

  it('close button has accessible label', () => {
    const { getByRole } = render(
      <Modal open={true} onClose={jest.fn()} title="My modal" />
    )
    const closeBtn = getByRole('button', { name: /close/i })
    expect(closeBtn).toBeInTheDocument()
  })

  it('has no accessibility violations with confirm/cancel buttons', async () => {
    const { container } = render(
      <Modal
        open={true}
        onClose={jest.fn()}
        title="Remove connection"
        description="This will disconnect your utility account."
        confirmLabel="Remove"
        cancelLabel="Keep connection"
        onConfirm={jest.fn()}
      />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with danger variant', async () => {
    const { container } = render(
      <Modal
        open={true}
        onClose={jest.fn()}
        title="Delete all data"
        description="This action is irreversible."
        confirmLabel="Delete permanently"
        onConfirm={jest.fn()}
        variant="danger"
      />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('renders nothing when closed and has no violations', async () => {
    const { container } = render(
      <Modal open={false} onClose={jest.fn()} title="Hidden modal" />
    )
    expect(container.querySelector('[role="dialog"]')).not.toBeInTheDocument()
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
