import React from "react";
import { cn } from "@/lib/utils";

interface CardHeaderProps {
  title: string;
  action?: React.ReactNode;
  className?: string;
  titleClassName?: string;
}

// shadcn 风格卡片头部：白底 + 底部细边框分隔，标题深色文字，右侧操作区
export function CardHeader({ title, action, className, titleClassName }: CardHeaderProps) {
  return (
    <div className={cn("flex items-center justify-between border-b bg-card px-5 py-3", className)}>
      <h3 className={cn("font-semibold text-foreground", titleClassName ?? "text-lg")}>{title}</h3>
      {action}
    </div>
  );
}
