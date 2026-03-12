/**
 * FTC-compliant affiliate disclosure.
 *
 * Must appear on any page that shows supplier recommendations
 * where we earn a commission from referrals.
 */

interface FTCDisclosureProps {
  variant?: 'inline' | 'banner'
}

export function FTCDisclosure({ variant = 'inline' }: FTCDisclosureProps) {
  if (variant === 'banner') {
    return (
      <div
        className="rounded border border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800"
        role="note"
        aria-label="Affiliate disclosure"
      >
        <strong>Disclosure:</strong> We may earn a commission when you switch
        suppliers through our links. This does not affect our rate comparisons
        or the order in which suppliers are displayed.
      </div>
    )
  }

  return (
    <p
      className="text-xs text-muted-foreground"
      role="note"
      aria-label="Affiliate disclosure"
    >
      We may earn a commission when you switch suppliers through our links. Rates
      and rankings are not affected.
    </p>
  )
}
