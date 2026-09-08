import { cn } from '@/lib/utils';

interface EmptyStateProps {
  message: string;
  className?: string;
}

export function EmptyState({ message, className }: EmptyStateProps) {
  return (
    <p className={cn('px-5 py-8 text-center text-xs text-muted-foreground', className)}>
      {message}
    </p>
  );
}
