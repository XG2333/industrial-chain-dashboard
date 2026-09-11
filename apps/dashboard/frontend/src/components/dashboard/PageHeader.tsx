import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  compact?: boolean;
  className?: string;
}

export function PageHeader({
  title,
  description,
  actions,
  compact = false,
  className,
}: PageHeaderProps) {
  return (
    <header className={cn('flex flex-wrap items-center justify-between gap-3', className)}>
      <div className="min-w-0">
        <h1
          className={cn(
            'font-bold tracking-tight text-slate-900 dark:text-white',
            compact ? 'text-base' : 'text-2xl md:text-3xl',
          )}
        >
          {title}
        </h1>
        {description && !compact && (
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{description}</p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-3">{actions}</div>}
    </header>
  );
}
