import type { ReactNode } from 'react';
import { Card } from 'flowbite-react';

interface DashboardCardProps {
  title?: string;
  action?: ReactNode;
  header?: ReactNode;
  children: ReactNode;
  className?: string;
  contentClassName?: string;
}

export function DashboardCard({
  title,
  action,
  header,
  children,
  className,
  contentClassName = 'p-5',
}: DashboardCardProps) {
  return (
    <Card className={className}>
      {header ?? (
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-5 py-3 dark:border-slate-700">
          <h2 className="text-sm font-semibold text-slate-900 dark:text-white">{title}</h2>
          {action}
        </div>
      )}
      <div className={contentClassName}>{children}</div>
    </Card>
  );
}
