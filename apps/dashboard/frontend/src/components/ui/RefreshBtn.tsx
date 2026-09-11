import { RefreshCw } from "lucide-react";

// 全页面统一的「刷新」小方框按钮: 描边圆角 + 灰字,
// 用于各数据区块(自选/行情/仓单/成交持仓/新闻/研报/行业数据)的手动刷新,
// 避免各区块自行造轮子导致的样式漂移。
export function RefreshBtn({
  onClick,
  loading = false,
  label = "刷新",
  title,
  disabled,
  className,
}: {
  onClick: () => void;
  loading?: boolean;
  label?: string;
  title?: string;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || loading}
      title={title ?? (loading ? "刷新中…" : "立即刷新数据")}
      className={
        "flex shrink-0 items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-xs font-medium text-muted-foreground transition hover:bg-muted/40 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50 " +
        (className ?? "")
      }
    >
      <RefreshCw className={"h-3 w-3 " + (loading ? "animate-spin" : "")} />
      {loading ? "刷新中…" : label}
    </button>
  );
}
