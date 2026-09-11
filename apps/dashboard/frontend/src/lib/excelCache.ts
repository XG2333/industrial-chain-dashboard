import type { ChartData } from "./chartTypes";

const CACHE_TTL_MS = 30 * 60 * 1000;
const BATCH_SIZE = 100;

interface CacheEntry {
  chart: ChartData;
  loadedAt: number;
}

interface PendingWaiter {
  ids: string[];
  resolve: (charts: ChartData[]) => void;
  reject: (error: Error) => void;
}

const seriesCache = new Map<string, CacheEntry>();
let pendingIds = new Set<string>();
let pendingWaiters: PendingWaiter[] = [];
let flushTimer: number | null = null;

async function fetchChartBatch(ids: string[]): Promise<ChartData[]> {
  const response = await fetch("/api/battery/excel/charts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids }),
  });
  if (!response.ok) {
    throw new Error(`chart batch request failed: ${response.status}`);
  }
  const payload = (await response.json()) as { charts?: ChartData[] };
  return payload.charts || [];
}

function scheduleFlush(): void {
  if (flushTimer !== null) return;
  flushTimer = window.setTimeout(() => {
    flushTimer = null;
    void flushPending();
  }, 0);
}

async function flushPending(): Promise<void> {
  const ids = [...pendingIds];
  const waiters = pendingWaiters;
  pendingIds = new Set();
  pendingWaiters = [];

  if (ids.length === 0) return;

  try {
    const batches: string[][] = [];
    for (let index = 0; index < ids.length; index += BATCH_SIZE) {
      batches.push(ids.slice(index, index + BATCH_SIZE));
    }
    const loaded = (await Promise.all(batches.map(fetchChartBatch))).flat();
    const loadedAt = Date.now();
    const byId = new Map<string, ChartData>();
    for (const chart of loaded) {
      seriesCache.set(chart.id, { chart, loadedAt });
      byId.set(chart.id, chart);
    }
    for (const waiter of waiters) {
      waiter.resolve(
        waiter.ids
          .map((id) => byId.get(id))
          .filter((chart): chart is ChartData => Boolean(chart)),
      );
    }
  } catch (error) {
    const wrapped = error instanceof Error ? error : new Error(String(error));
    for (const waiter of waiters) {
      waiter.reject(wrapped);
    }
  }
}

export function loadChartData(ids: string[]): Promise<ChartData[]> {
  const uniqueIds = [...new Set(ids)];
  const now = Date.now();
  const cached = uniqueIds
    .map((id) => {
      const entry = seriesCache.get(id);
      return entry && now - entry.loadedAt < CACHE_TTL_MS ? entry.chart : undefined;
    })
    .filter((chart): chart is ChartData => Boolean(chart));
  const missing = uniqueIds.filter((id) => {
    const entry = seriesCache.get(id);
    return !entry || now - entry.loadedAt >= CACHE_TTL_MS;
  });

  if (missing.length === 0) {
    return Promise.resolve(cached);
  }

  return new Promise((resolve, reject) => {
    pendingWaiters.push({ ids: missing, resolve, reject });
    missing.forEach((id) => pendingIds.add(id));
    scheduleFlush();
  });
}

export function clearChartSeriesCache(): void {
  seriesCache.clear();
  pendingIds.clear();
  pendingWaiters = [];
}
