import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg border text-sm font-medium transition-colors duration-150 touch-manipulation focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--ui-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[color:var(--ui-bg)] disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        default:
          'border-[color:var(--ui-accent)] bg-[color:var(--ui-accent)] text-white shadow-[0_0_0_1px_rgba(11,14,18,0.32)_inset] hover:border-[color:var(--ui-accent-strong)] hover:bg-[color:var(--ui-accent-strong)]',
        destructive:
          'border-[#944747] bg-[#8f3f3f] text-[#fde6e6] hover:border-[#a65050] hover:bg-[#9f4b4b]',
        outline:
          'border-[color:var(--ui-border-strong)] bg-transparent text-[color:var(--ui-text)] hover:border-[color:var(--ui-accent)] hover:bg-[color:var(--ui-accent-soft)]',
        secondary:
          'border-[color:var(--ui-border)] bg-[color:var(--ui-surface-2)] text-[color:var(--ui-text)] hover:border-[color:var(--ui-border-strong)] hover:bg-[color:var(--ui-surface-3)]',
        ghost:
          'border-transparent bg-transparent text-[color:var(--ui-text-dim)] hover:border-[color:var(--ui-border)] hover:bg-[color:var(--ui-surface-1)] hover:text-[color:var(--ui-text)]',
        link:
          'border-transparent bg-transparent p-0 text-[#7ea1ff] underline-offset-4 hover:text-[#9bb7ff] hover:underline',
      },
      size: {
        default: 'min-h-11 px-4 py-2 md:h-9 md:min-h-0',
        sm: 'min-h-11 px-3 py-2 text-xs md:h-8 md:min-h-0',
        lg: 'min-h-11 px-8 py-2.5 md:h-10 md:min-h-0',
        icon: 'h-11 w-11 md:h-9 md:w-9',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return (
      <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    )
  }
)
Button.displayName = 'Button'

export { Button, buttonVariants }
