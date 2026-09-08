// 板块速评"一键分析全部"的轻量发布订阅（模块级单例，跨组件通信）。
// 协调器（SectorAnalysisAllToolbar）逐个触发 run(key)，各板块的 SectorQuickAnalysis
// 订阅自己的 key；分析结束（成功或失败）后广播 done(key)，协调器据此进入下一个板块。

type Handler = (key: string) => void;

const runHandlers = new Map<string, Set<Handler>>();
const doneHandlers = new Set<Handler>();

export const quickAnalysisBus = {
  // 板块组件订阅：收到 run 事件时开始本板块分析
  onRun(key: string, h: Handler) {
    if (!runHandlers.has(key)) runHandlers.set(key, new Set());
    runHandlers.get(key)!.add(h);
  },
  offRun(key: string, h: Handler) {
    runHandlers.get(key)?.delete(h);
  },
  // 触发某板块开始分析（协调器调用；key = 板块缓存键）
  run(key: string) {
    const handlers = runHandlers.get(key);
    if (handlers) {
      for (const h of handlers) h(key);
    }
  },
  // 协调器监听"某板块完成"
  onDone(h: Handler) {
    doneHandlers.add(h);
  },
  offDone(h: Handler) {
    doneHandlers.delete(h);
  },
  done(key: string) {
    for (const h of doneHandlers) h(key);
  },
};
