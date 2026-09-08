import { cn } from '@/lib/utils';
import { isExportMode, exportUrl } from '@/lib/exportMode';

interface IndustryTabBarProps {
  tabs: string[];
  activeTab: string;
  onChange: (tab: string) => void;
  className?: string;
}

export function IndustryTabBar({
  tabs,
  activeTab,
  onChange,
  className,
}: IndustryTabBarProps) {
  const isExport = isExportMode();
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
            {tab}
          </button>
        ))}
        <button
          type="button"
          onClick={() => {
            window.location.href = exportUrl(!isExport);
          }}
          className="ml-auto flex items-center gap-1 rounded-lg border border-border bg-background px-4 py-2 text-sm font-medium text-muted-foreground transition hover:bg-accent hover:text-accent-foreground print-hide"
          title={isExport ? '返回正常浏览模式' : '进入导出模式:全量渲染图表供打印为 PDF'}
        >
          {isExport ? '退出导出模式' : '导出 PDF'}
        </button>
      </div>
      {isExport && (
        <div className="rounded-md border border-primary/40 bg-primary/10 px-3 py-1.5 text-xs leading-relaxed text-primary print-hide">
          导出模式：全部图表已强制加载（下方骨架屏消失即就绪）。请执行
          浏览器「打印 Ctrl+P」→ 目标选「另存为 PDF」，边距可设「无」、勾选「背景图形」；
          悬浮索引与按钮已在打印时自动隐藏，长表格/长列表已自动展开不截断。
          完成后点右上「退出导出模式」返回。
        </div>
      )}
    </div>
  );
}
