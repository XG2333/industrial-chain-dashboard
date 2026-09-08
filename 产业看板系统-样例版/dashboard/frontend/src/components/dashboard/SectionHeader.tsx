import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface SectionHeaderProps {
  title: string;
  action?: ReactNode;
  className?: string;
}

export function SectionHeader({ title, action, className }: SectionHeaderProps) {
  return (
    <div
      className={cn(
        'flex items-center justify-between gap-3 border-b border-slate-200 px-5 py-3 dark:border-slate-700',
        className,
      )}
    >
      <h2 className="text-sm font-semibold text-slate-900 dark:text-white">{title}</h2>
      {action}
    </div>
  );
}
