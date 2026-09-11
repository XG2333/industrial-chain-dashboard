import { Fragment } from "react";

// 板块简评结论渲染：纯文本基础上做轻量 markdown 处理——
// "**加粗**"渲染为粗体（AI 常用强调），换行/空格由调用方 whitespace 类控制。
export function ConclusionText({ text, className }: { text: string; className?: string }) {
  const parts = (text || "").split(/\*\*/);
  // ** 成对出现：奇数索引段为加粗内容；不成对时多出的段原样显示
  return (
    <p className={className}>
      {parts.map((part, i) =>
        i % 2 === 1 && part ? (
          <strong key={i} className="font-bold text-slate-800">
            {part}
          </strong>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </p>
  );
}
