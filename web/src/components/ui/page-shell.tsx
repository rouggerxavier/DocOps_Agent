import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

export function PageShell({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn('app-page', className)}>{children}</div>
}

export function PageHeader({
  title,
  subtitle,
  actions,
  className,
}: {
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  className?: string
}) {
  return (
    <header className={cn('app-page-header', className)}>
      <div>
        <h1 className="app-page-title">{title}</h1>
        {subtitle ? <p className="app-page-subtitle">{subtitle}</p> : null}
      </div>
      {actions ? <div className="shrink-0">{actions}</div> : null}
    </header>
  )
}

export function SectionKicker({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn('app-kicker', className)}>{children}</p>
}
