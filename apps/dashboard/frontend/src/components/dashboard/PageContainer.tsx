import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface PageContainerProps {
  children: ReactNode;
  className?: string;
  maxWidth?: 'default' | 'wide';
}

export function PageContainer({
  children,
  className,
  maxWidth = 'default',
}: PageContainerProps) {
  return (
    <div
      className={cn(
        'mx-auto w-full p-6',
        maxWidth === 'wide' ? 'max-w-[1600px] space-y-6' : 'max-w-7xl space-y-8',
        className,
      )}
    >
      {children}
    </div>
  );
}
