import { useState } from "react";
import { Bot } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { CardHeader } from "@/components/ui/CardHeader";
import { ConclusionText } from "@/components/charts/ConclusionText";

// 板块简评（结构化版）：AI 返回 summary(verdict/key_points/outlook) 时渲染为
// 状态块 → 关键逻辑要点 → 前瞻 的分层卡片（与板块/仓单速评视觉语言一致）；
// 旧缓存或 AI 未返回 summary 时降级为整段结论文本；"查看全文"折叠完整段落。

export interface BriefKeyPoint {
  title: string;
  text: string;
}

export interface BriefSummary {
  verdict: string;
  key_points: BriefKeyPoint[];
  outlook: string;
}

export interface BriefAnalysis {
  scores: { dimension: string; score: number; reason: string }[];
  conclusion: string;
  summary?: BriefSummary | null;
  at?: number;
}

interface BriefPanelProps {
  analysis: BriefAnalysis | null;
  analyzing: boolean;
  error: string | null;
  onAnalyze: () => void;
}

export function BriefPanel({ analysis, analyzing, error, onAnalyze }: BriefPanelProps) {
  const [showFull, setShowFull] = useState(false);
  const summary = analysis?.summary;

  return (
    <div className="rounded-xl border bg-card">
      <CardHeader
        title="板块简评"
        action={
          <Button variant="outline" onClick={onAnalyze} disabled={analyzing}>
            <Bot className={"h-3.5 w-3.5 " + (analyzing ? "animate-pulse" : "")} />
            {analyzing ? "分析中…" : analysis ? "重新分析" : "AI 分析"}
          </Button>
        }
      />
      <div className="p-4">
        {!analysis && !error && (
          <p className="py-6 text-center text-xs text-muted-foreground">
            点击「AI 分析」让 DeepSeek 生成板块简评
          </p>
        )}
        {error && <p className="py-6 text-center text-xs text-red-500">AI 分析失败：{error}</p>}
        {analysis && (
          <div className="space-y-3">
            {summary?.verdict ? (
              <>
                {/* 状态判断（主导逻辑） */}
                <div className="rounded-md border border-border bg-muted/30 px-3 py-2.5">
                  <p className="text-lg font-semibold leading-relaxed text-foreground">{summary.verdict}</p>
                </div>
                {/* 关键逻辑要点 */}
                {summary.key_points.length > 0 && (
                  <ul className="space-y-2">
                    {summary.key_points.map((p, i) => (
                      <li key={i} className="flex items-baseline gap-2 text-[15px] leading-relaxed">
                        <span className="shrink-0 select-none font-bold text-primary">{i + 1}.</span>
                        {p.title && <span className="shrink-0 font-semibold text-foreground">{p.title}</span>}
                        <span className="text-muted-foreground">{p.text}</span>
                      </li>
                    ))}
                  </ul>
                )}
                {/* 前瞻判断 */}
                {summary.outlook && (
                  <div className="flex items-baseline gap-2 border-t border-border/70 pt-2">
                    <span className="shrink-0 text-sm font-bold tracking-widest text-muted-foreground">前瞻</span>
                    <p className="text-[15px] leading-relaxed text-foreground/90">{summary.outlook}</p>
                  </div>
                )}
                {/* 完整结论段落：折叠展示 */}
                {analysis.conclusion && (
                  <div className="border-t border-border/60 pt-1.5">
                    <button
                      onClick={() => setShowFull((v) => !v)}
                      className="text-xs text-muted-foreground underline decoration-dotted underline-offset-2 hover:text-foreground"
                    >
                      {showFull ? "收起全文" : "查看全文"}
                    </button>
                    {showFull && (
                      <div className="mt-1.5">
                        <ConclusionText
                          text={analysis.conclusion}
                          className="whitespace-pre-wrap text-[15px] leading-relaxed text-slate-700"
                        />
                      </div>
                    )}
                  </div>
                )}
              </>
            ) : (
              /* 旧缓存 / AI 未返回 summary：整段结论降级展示 */
              analysis.conclusion && (
                <ConclusionText
                  text={analysis.conclusion}
                  className="whitespace-pre-wrap text-[20px] leading-relaxed text-slate-700"
                />
              )
            )}
            {analysis.at != null && (
              <p className="text-xs text-muted-foreground">
                AI 生成于{" "}
                {new Date(analysis.at).toLocaleString("zh-CN", { hour12: false })}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
