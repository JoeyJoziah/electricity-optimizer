import { render, screen } from '@testing-library/react'
import { SavingsTracker } from '@/components/gamification/SavingsTracker'
import '@testing-library/jest-dom'

// Mock cn utility
jest.mock('@/lib/utils/cn', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

// Mock lucide-react icons
jest.mock('lucide-react', () => ({
  TrendingUp: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-trending" {...props} />,
  Flame: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-flame" {...props} />,
  Target: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-target" {...props} />,
  Award: (props: React.SVGAttributes<SVGElement>) => <svg data-testid="icon-award" {...props} />,
}))

// Mock formatCurrency - the real one uses USD by default
jest.mock('@/lib/utils/format', () => ({
  formatCurrency: (amount: number) => `$${amount.toFixed(2)}`,
}))

const defaultProps = {
  dailySavings: 1.50,
  weeklySavings: 8.75,
  monthlySavings: 32.00,
  streakDays: 5,
  bestStreak: 12,
  optimizationScore: 72,
}

describe('SavingsTracker', () => {
  it('renders the savings tracker container', () => {
    render(<SavingsTracker {...defaultProps} />)

    expect(screen.getByTestId('savings-tracker')).toBeInTheDocument()
  })

  it('displays daily savings with correct USD formatting', () => {
    render(<SavingsTracker {...defaultProps} />)

    expect(screen.getByText('$1.50')).toBeInTheDocument()
    expect(screen.getByText('Today')).toBeInTheDocument()
  })

  it('displays weekly savings with correct formatting', () => {
    render(<SavingsTracker {...defaultProps} />)

    expect(screen.getByText('$8.75')).toBeInTheDocument()
    expect(screen.getByText('This Week')).toBeInTheDocument()
  })

  it('displays monthly savings with correct formatting', () => {
    render(<SavingsTracker {...defaultProps} />)

    expect(screen.getByText('$32.00')).toBeInTheDocument()
    expect(screen.getByText('This Month')).toBeInTheDocument()
  })

  it('displays current streak days', () => {
    render(<SavingsTracker {...defaultProps} />)

    expect(screen.getByText('5-day streak')).toBeInTheDocument()
  })

  it('displays best streak', () => {
    render(<SavingsTracker {...defaultProps} />)

    expect(screen.getByText('Best: 12 days')).toBeInTheDocument()
  })

  it('displays optimization score', () => {
    render(<SavingsTracker {...defaultProps} />)

    expect(screen.getByText('72/100')).toBeInTheDocument()
    expect(screen.getByText('Optimization Score')).toBeInTheDocument()
  })

  it('shows bronze tier for streak under 7 days', () => {
    render(<SavingsTracker {...defaultProps} streakDays={3} />)

    const streakSection = screen.getByText('3-day streak').closest('div[class]')
    expect(streakSection?.className).toContain('text-amber-600')
  })

  it('shows silver tier for streak of 7+ days', () => {
    render(<SavingsTracker {...defaultProps} streakDays={10} />)

    const streakSection = screen.getByText('10-day streak').closest('div[class]')
    expect(streakSection?.className).toContain('text-gray-500')
  })

  it('shows gold tier for streak of 14+ days', () => {
    render(<SavingsTracker {...defaultProps} streakDays={20} />)

    const streakSection = screen.getByText('20-day streak').closest('div[class]')
    expect(streakSection?.className).toContain('text-yellow-600')
  })

  it('shows legendary tier for streak of 30+ days', () => {
    render(<SavingsTracker {...defaultProps} streakDays={35} />)

    const streakSection = screen.getByText('35-day streak').closest('div[class]')
    expect(streakSection?.className).toContain('text-purple-600')
  })

  it('shows progress bar percentage correctly', () => {
    // monthlySavings of 32 out of goal of 50 = 64%
    render(<SavingsTracker {...defaultProps} />)

    expect(screen.getByText('64%')).toBeInTheDocument()
  })

  it('displays monthly goal of $50', () => {
    render(<SavingsTracker {...defaultProps} />)

    expect(screen.getByText(/Monthly Goal: \$50\.00/)).toBeInTheDocument()
  })

  it('caps progress bar at 100%', () => {
    render(<SavingsTracker {...defaultProps} monthlySavings={75} />)

    expect(screen.getByText('100%')).toBeInTheDocument()
  })
})
