import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardContent, CardDescription, CardFooter } from '@/components/ui/card'
import { Input, Checkbox } from '@/components/ui/input'
import { Skeleton, CardSkeleton, ChartSkeleton } from '@/components/ui/skeleton'
import '@testing-library/jest-dom'

// Mock cn utility
jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

// Mock lucide-react Loader2 for Button
jest.mock('lucide-react', () => ({
  Loader2: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="loader-icon" {...props} />,
}))

// ---- Badge Tests ----
describe('Badge', () => {
  it('renders children text', () => {
    render(<Badge>Active</Badge>)
    expect(screen.getByText('Active')).toBeInTheDocument()
  })

  it('applies default variant class', () => {
    render(<Badge>Default</Badge>)
    const badge = screen.getByText('Default')
    expect(badge.className).toContain('bg-gray-100')
  })

  it('applies success variant class', () => {
    render(<Badge variant="success">Success</Badge>)
    const badge = screen.getByText('Success')
    expect(badge.className).toContain('bg-success-100')
  })

  it('applies warning variant class', () => {
    render(<Badge variant="warning">Warning</Badge>)
    const badge = screen.getByText('Warning')
    expect(badge.className).toContain('bg-warning-100')
  })

  it('applies danger variant class', () => {
    render(<Badge variant="danger">Error</Badge>)
    const badge = screen.getByText('Error')
    expect(badge.className).toContain('bg-danger-100')
  })

  it('applies info variant class', () => {
    render(<Badge variant="info">Info</Badge>)
    const badge = screen.getByText('Info')
    expect(badge.className).toContain('bg-primary-100')
  })

  it('forwards className prop', () => {
    render(<Badge className="custom-class">Custom</Badge>)
    const badge = screen.getByText('Custom')
    expect(badge.className).toContain('custom-class')
  })

  it('applies sm size by default', () => {
    render(<Badge>Small</Badge>)
    const badge = screen.getByText('Small')
    expect(badge.className).toContain('text-xs')
  })

  it('applies md size class', () => {
    render(<Badge size="md">Medium</Badge>)
    const badge = screen.getByText('Medium')
    expect(badge.className).toContain('text-sm')
  })
})

// ---- Button Tests ----
describe('Button', () => {
  it('renders children text', () => {
    render(<Button>Click me</Button>)
    expect(screen.getByRole('button', { name: 'Click me' })).toBeInTheDocument()
  })

  it('calls onClick handler when clicked', async () => {
    const onClick = jest.fn()
    const user = userEvent.setup()

    render(<Button onClick={onClick}>Click me</Button>)
    await user.click(screen.getByRole('button', { name: 'Click me' }))

    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('is disabled when disabled prop is true', () => {
    render(<Button disabled>Disabled</Button>)
    expect(screen.getByRole('button', { name: 'Disabled' })).toBeDisabled()
  })

  it('is disabled when loading prop is true', () => {
    render(<Button loading>Loading</Button>)
    expect(screen.getByRole('button', { name: 'Loading' })).toBeDisabled()
  })

  it('shows loader icon when loading', () => {
    render(<Button loading>Loading</Button>)
    expect(screen.getByTestId('loader-icon')).toBeInTheDocument()
  })

  it('applies primary variant by default', () => {
    render(<Button>Primary</Button>)
    const button = screen.getByRole('button', { name: 'Primary' })
    expect(button.className).toContain('bg-primary-600')
  })

  it('applies secondary variant', () => {
    render(<Button variant="secondary">Secondary</Button>)
    const button = screen.getByRole('button', { name: 'Secondary' })
    expect(button.className).toContain('bg-gray-100')
  })

  it('applies outline variant', () => {
    render(<Button variant="outline">Outline</Button>)
    const button = screen.getByRole('button', { name: 'Outline' })
    expect(button.className).toContain('border')
  })

  it('applies ghost variant', () => {
    render(<Button variant="ghost">Ghost</Button>)
    const button = screen.getByRole('button', { name: 'Ghost' })
    expect(button.className).toContain('hover:bg-gray-100')
  })

  it('applies danger variant', () => {
    render(<Button variant="danger">Danger</Button>)
    const button = screen.getByRole('button', { name: 'Danger' })
    expect(button.className).toContain('bg-danger-600')
  })

  it('applies size sm', () => {
    render(<Button size="sm">Small</Button>)
    const button = screen.getByRole('button', { name: 'Small' })
    expect(button.className).toContain('text-sm')
  })

  it('applies size lg', () => {
    render(<Button size="lg">Large</Button>)
    const button = screen.getByRole('button', { name: 'Large' })
    expect(button.className).toContain('text-lg')
  })

  it('forwards className prop', () => {
    render(<Button className="extra-class">Custom</Button>)
    const button = screen.getByRole('button', { name: 'Custom' })
    expect(button.className).toContain('extra-class')
  })

  it('renders left icon', () => {
    render(<Button leftIcon={<span data-testid="left">L</span>}>With Icon</Button>)
    expect(screen.getByTestId('left')).toBeInTheDocument()
  })

  it('renders right icon', () => {
    render(<Button rightIcon={<span data-testid="right">R</span>}>With Icon</Button>)
    expect(screen.getByTestId('right')).toBeInTheDocument()
  })

  it('hides right icon when loading', () => {
    render(<Button loading rightIcon={<span data-testid="right">R</span>}>Loading</Button>)
    expect(screen.queryByTestId('right')).not.toBeInTheDocument()
  })
})

// ---- Card Tests ----
describe('Card', () => {
  it('renders children', () => {
    render(<Card>Card content</Card>)
    expect(screen.getByText('Card content')).toBeInTheDocument()
  })

  it('applies bordered variant by default', () => {
    render(<Card>Bordered</Card>)
    const card = screen.getByText('Bordered').closest('div')
    expect(card?.className).toContain('border')
  })

  it('applies elevated variant', () => {
    render(<Card variant="elevated">Elevated</Card>)
    const card = screen.getByText('Elevated').closest('div')
    expect(card?.className).toContain('shadow-lg')
  })

  it('forwards className prop', () => {
    render(<Card className="my-card">Custom</Card>)
    const card = screen.getByText('Custom').closest('div')
    expect(card?.className).toContain('my-card')
  })

  it('renders CardHeader', () => {
    render(<CardHeader>Header</CardHeader>)
    expect(screen.getByText('Header')).toBeInTheDocument()
  })

  it('renders CardTitle as h3 by default', () => {
    render(<CardTitle>Title</CardTitle>)
    const title = screen.getByText('Title')
    expect(title.tagName).toBe('H3')
  })

  it('renders CardTitle with custom heading level', () => {
    render(<CardTitle as="h2">Title H2</CardTitle>)
    const title = screen.getByText('Title H2')
    expect(title.tagName).toBe('H2')
  })

  it('renders CardContent', () => {
    render(<CardContent>Content body</CardContent>)
    expect(screen.getByText('Content body')).toBeInTheDocument()
  })

  it('renders CardDescription', () => {
    render(<CardDescription>Description text</CardDescription>)
    expect(screen.getByText('Description text')).toBeInTheDocument()
  })

  it('renders CardFooter', () => {
    render(<CardFooter>Footer content</CardFooter>)
    expect(screen.getByText('Footer content')).toBeInTheDocument()
  })
})

// ---- Input Tests ----
describe('Input', () => {
  it('renders an input element', () => {
    render(<Input placeholder="Enter text" />)
    expect(screen.getByPlaceholderText('Enter text')).toBeInTheDocument()
  })

  it('renders with a label', () => {
    render(<Input label="Username" />)
    expect(screen.getByLabelText('Username')).toBeInTheDocument()
  })

  it('handles value changes', async () => {
    const onChange = jest.fn()
    const user = userEvent.setup()

    render(<Input placeholder="Type here" onChange={onChange} />)
    await user.type(screen.getByPlaceholderText('Type here'), 'hello')

    expect(onChange).toHaveBeenCalledTimes(5)
  })

  it('shows error message when error prop is set', () => {
    render(<Input label="Email" error="Invalid email" />)

    expect(screen.getByText('Invalid email')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('sets aria-invalid when error is present', () => {
    render(<Input label="Email" error="Required" />)

    const input = screen.getByLabelText('Email')
    expect(input).toHaveAttribute('aria-invalid', 'true')
  })

  it('shows helper text when provided', () => {
    render(<Input label="Name" helperText="Enter your full name" />)

    expect(screen.getByText('Enter your full name')).toBeInTheDocument()
  })

  it('hides helper text when error is present', () => {
    render(<Input label="Name" helperText="Enter your full name" error="Required" />)

    expect(screen.queryByText('Enter your full name')).not.toBeInTheDocument()
    expect(screen.getByText('Required')).toBeInTheDocument()
  })

  it('forwards className prop', () => {
    render(<Input className="custom-input" placeholder="test" />)
    const input = screen.getByPlaceholderText('test')
    expect(input.className).toContain('custom-input')
  })
})

// ---- Checkbox Tests ----
describe('Checkbox', () => {
  it('renders with a label', () => {
    render(<Checkbox label="Accept terms" />)
    expect(screen.getByLabelText('Accept terms')).toBeInTheDocument()
  })

  it('is a checkbox input', () => {
    render(<Checkbox label="Accept terms" />)
    const checkbox = screen.getByLabelText('Accept terms')
    expect(checkbox).toHaveAttribute('type', 'checkbox')
  })

  it('handles change events', async () => {
    const onChange = jest.fn()
    const user = userEvent.setup()

    render(<Checkbox label="Accept" onChange={onChange} />)
    await user.click(screen.getByLabelText('Accept'))

    expect(onChange).toHaveBeenCalledTimes(1)
  })
})

// ---- Skeleton Tests ----
describe('Skeleton', () => {
  it('renders with default text variant', () => {
    const { container } = render(<Skeleton />)
    const skeleton = container.firstChild as HTMLElement
    expect(skeleton.className).toContain('animate-pulse')
    expect(skeleton.className).toContain('rounded')
  })

  it('applies circular variant', () => {
    const { container } = render(<Skeleton variant="circular" />)
    const skeleton = container.firstChild as HTMLElement
    expect(skeleton.className).toContain('rounded-full')
  })

  it('applies rectangular variant', () => {
    const { container } = render(<Skeleton variant="rectangular" />)
    const skeleton = container.firstChild as HTMLElement
    expect(skeleton.className).toContain('rounded-lg')
  })

  it('applies custom width and height in pixels', () => {
    const { container } = render(<Skeleton width={100} height={50} />)
    const skeleton = container.firstChild as HTMLElement
    expect(skeleton.style.width).toBe('100px')
    expect(skeleton.style.height).toBe('50px')
  })

  it('applies custom width and height as strings', () => {
    const { container } = render(<Skeleton width="50%" height="2rem" />)
    const skeleton = container.firstChild as HTMLElement
    expect(skeleton.style.width).toBe('50%')
    expect(skeleton.style.height).toBe('2rem')
  })

  it('forwards className prop', () => {
    const { container } = render(<Skeleton className="my-skeleton" />)
    const skeleton = container.firstChild as HTMLElement
    expect(skeleton.className).toContain('my-skeleton')
  })

  it('renders CardSkeleton with multiple skeleton lines', () => {
    const { container } = render(<CardSkeleton />)
    const skeletons = container.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThanOrEqual(3)
  })

  it('renders ChartSkeleton', () => {
    const { container } = render(<ChartSkeleton />)
    const skeletons = container.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThanOrEqual(1)
  })
})
