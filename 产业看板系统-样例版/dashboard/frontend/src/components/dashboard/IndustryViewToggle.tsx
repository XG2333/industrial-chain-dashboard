import { cn } from '@/lib/utils';

export type IndustryView = '行业研究' | '个股标的';

interface IndustryViewToggleProps {
  value: IndustryView;
  onChange: (view: IndustryView) => void;
  className?: string;
}

export function IndustryViewToggle({
  value,
  onChange,
  className,
}: IndustryViewToggleProps) {
  return (
    <div className={cn('flex gap-2 pt-3', className)}>
      {(['行业研究', '个股标的'] as const).map((view) => (
        <button
          key={view}
          onClick={() => onChange(view)}
          className={cn(
            'rounded-lg px-5 py-2 text-xl font-semibold transition',
            value === view
              ? 'bg-primary text-primary-foreground'
              : 'border border-border bg-background text-muted-foreground hover:bg-accent hover:text-accent-foreground',
          )}
        >
          {view}
        </button>
      ))}
    </div>
  );
}
