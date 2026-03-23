import * as React from 'react'
import { cn } from '@/lib/utils'

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      className={cn(
        'flex min-h-11 w-full rounded-lg border px-3 py-2.5 text-sm shadow-sm transition-colors touch-manipulation md:h-9 md:min-h-0 md:py-1',
        'border-[color:var(--ui-border)] bg-[color:var(--ui-surface-2)] text-[color:var(--ui-text)] placeholder:text-[color:var(--ui-text-meta)]',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--ui-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[color:var(--ui-bg)] disabled:cursor-not-allowed disabled:opacity-50',
        className
      )}
      ref={ref}
      {...props}
    />
  )
)
Input.displayName = 'Input'

export { Input }
