import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold transition-colors',
  {
    variants: {
      variant: {
        default: 'border-[color:var(--ui-accent)] bg-[color:var(--ui-accent-soft)] text-[#8eaefc]',
        secondary: 'border-[color:var(--ui-border)] bg-[color:var(--ui-surface-2)] text-[color:var(--ui-text-dim)]',
        destructive: 'border-[#944747] bg-[#8f3f3f]/20 text-[#f1b1b1]',
        outline: 'border-[color:var(--ui-border-strong)] bg-transparent text-[color:var(--ui-text-meta)]',
      },
    },
    defaultVariants: { variant: 'default' },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge, badgeVariants }
