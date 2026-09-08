import type { ReactNode } from 'react';
import { Card } from 'flowbite-react';
import { cn } from '@/lib/utils';

interface KpiCardProps {
  title: string;
  value: string;
  changePct: number;
  detail?: ReactNode;
  className?: string;
}

export function KpiCard({ title, value, changePct, detail, className }: KpiCardProps) {
  const up = changePct > 0;
  const flat = changePct === 0;
  const toneClass = flat
    ? 'text-slate-500 dark:text-slate-400'
    : up
      ? 'text-red-600 dark:text-red-400'
      : 'text-green-600 dark:text-green-400';

  return (
    <Card className={cn('overflow-hidden', className)}>
      <div className="p-5">
        <p className="text-sm text-slate-500 dark:text-slate-400">{title}</p>
        <p className="mt-1 text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
          {value}
        </p>
        <div className="mt-1 flex items-center gap-2">
          <span className={cn('text-sm font-semibold', toneClass)}>
            {flat ? '0.00' : up ? '+' : ''}
            {changePct.toFixed(2)}%
          </span>
        </div>
        {detail && (
          <div className="mt-3 rounded-lg bg-slate-100 px-3 py-2 text-xs dark:bg-slate-700">
            {detail}
          </div>
        )}
      </div>
    </Card>
  );
}
