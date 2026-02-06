'use client'

import React from 'react'
import { cn } from '@/lib/utils/cn'

export interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'text' | 'circular' | 'rectangular'
  width?: string | number
  height?: string | number
}

export const Skeleton = React.forwardRef<HTMLDivElement, SkeletonProps>(
  ({ className, variant = 'text', width, height, style, ...props }, ref) => {
    const variantStyles = {
      text: 'rounded h-4',
      circular: 'rounded-full',
      rectangular: 'rounded-lg',
    }

    return (
      <div
        ref={ref}
        className={cn(
          'animate-pulse bg-gray-200',
          variantStyles[variant],
          className
        )}
        style={{
          width: typeof width === 'number' ? `${width}px` : width,
          height: typeof height === 'number' ? `${height}px` : height,
          ...style,
        }}
        {...props}
      />
    )
  }
)

Skeleton.displayName = 'Skeleton'

// Pre-built skeleton components for common patterns
export const CardSkeleton: React.FC = () => (
  <div className="rounded-xl border border-gray-200 bg-white p-4">
    <Skeleton variant="text" className="mb-4 h-6 w-1/3" />
    <Skeleton variant="text" className="mb-2 h-4 w-full" />
    <Skeleton variant="text" className="mb-2 h-4 w-5/6" />
    <Skeleton variant="text" className="h-4 w-2/3" />
  </div>
)

export const ChartSkeleton: React.FC<{ height?: number }> = ({
  height = 300,
}) => (
  <div className="rounded-xl border border-gray-200 bg-white p-4">
    <Skeleton variant="text" className="mb-4 h-6 w-1/4" />
    <Skeleton variant="rectangular" height={height} className="w-full" />
  </div>
)

export const TableRowSkeleton: React.FC<{ columns?: number }> = ({
  columns = 5,
}) => (
  <tr>
    {Array.from({ length: columns }).map((_, i) => (
      <td key={i} className="px-4 py-3">
        <Skeleton variant="text" className="h-4" />
      </td>
    ))}
  </tr>
)
