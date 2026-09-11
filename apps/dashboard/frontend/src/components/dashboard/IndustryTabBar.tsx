import { cn } from '@/lib/utils';

interface IndustryTabBarProps {
  tabs: string[];
  activeTab: string;
  onChange: (tab: string) => void;
  className?: string;
  // 按钮显示名覆盖(内部值不变, 如 "电解液产业链" 按钮显示为 "电解液")
  labels?: Record<string, string>;
}

export function IndustryTabBar({
  tabs,
  activeTab,
  onChange,
  className,
  labels,
}: IndustryTabBarProps) {
  return (
    <div className="space-y-2">
      <div className={cn('flex flex-wrap items-center gap-1.5', className)}>
        {tabs.map((tab) => (
          <button
            key={tab}
            onClick={() => onChange(tab)}
            className={cn(
              'rounded-lg px-5 py-2 text-xl font-semibold transition',
              activeTab === tab
                ? 'bg-primary text-primary-foreground'
                : 'border border-border bg-background text-muted-foreground hover:bg-accent hover:text-accent-foreground',
            )}
          >
            {labels && labels[tab] ? labels[tab] : tab}
          </button>
        ))}
      </div>
    </div>
  );
}
