import { useCallback, useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import {
  KpiCard,
  PageContainer,
  PageHeader,
} from "@/components/dashboard";
import { DashboardBadge } from "@/components/ui/DashboardBadge";
import { DashboardButton } from "@/components/ui/DashboardButton";
import { DashboardInfoBlock } from "@/components/ui/DashboardInfoBlock";

interface IndexQuote {
  code: string; name: string; price: number;
  change_pct: number; amount_yi: number;
  main_flow_yi?: number;
}

export function Overview() {
  const [indices, setIndices] = useState<IndexQuote[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState("");
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchAll = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true);
    try {
      const r1 = await fetch("/api/index-quotes");
      if (r1.ok) { const d = await r1.json(); setIndices(d.indices || []); }
      setLastUpdate(new Date().toLocaleTimeString("zh-CN", { hour12: false }));
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    fetchAll(true);
    timerRef.current = setInterval(() => fetchAll(false), 30_000);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [fetchAll]);
  const cc = (pct: number) => pct === 0 ? "text-muted-foreground" : pct > 0 ? "text-red-500" : "text-green-500";

  if (loading && indices.length === 0) {
    return <div className="flex h-[60vh] items-center justify-center text-muted-foreground"><p className="text-lg">加载行情中…</p></div>;
  }
  if (error) {
    return <div className="flex flex-col items-center justify-center h-[60vh] gap-3"><p className="text-red-500">{error}</p><button onClick={() => fetchAll(true)} className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm">重试</button></div>;
  }

  return (
    <PageContainer>
      {/* Header */}
      <PageHeader
        title="行情总览"
        actions={
          <>
            {lastUpdate && (
              <>
                <span className="text-xs text-muted-foreground">更新于 {lastUpdate}</span>
                <DashboardBadge>数据已更新</DashboardBadge>
              </>
            )}
            <DashboardButton
              onClick={() => fetchAll(true)}
              disabled={loading}
              className="gap-1.5"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
              刷新
            </DashboardButton>
          </>
        }
      />
      <DashboardInfoBlock>行情总览数据已更新，自动刷新已开启。</DashboardInfoBlock>

      {/* ── 行情总览: Index Cards ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {indices.map(idx => {
          return (
            <KpiCard
              key={idx.code}
              title={idx.name}
              value={idx.price.toFixed(2)}
              changePct={idx.change_pct}
              detail={
                <div className="flex items-center justify-between gap-2">
                  <span>
                    <span className="text-muted-foreground">成交额 </span>
                    <span className="font-semibold">{idx.amount_yi.toFixed(2)} 亿</span>
                  </span>
                {idx.main_flow_yi != null && (
                  <span>
                    <span className="text-muted-foreground">主力 </span>
                    <span className={`font-semibold ${idx.main_flow_yi >= 0 ? 'text-red-500' : 'text-green-500'}`}>
                      {idx.main_flow_yi >= 0 ? '+' : ''}{idx.main_flow_yi.toFixed(2)} 亿
                    </span>
                  </span>
                )}
                </div>
              }
            />
          );
        })}
      </div>

    </PageContainer>
  );
}
