import { useCallback, useState } from "react";

export type LayoutMode = "1" | "2";

export function useLayoutMode() {
  const [mode, setMode] = useState<LayoutMode>(() => {
    const saved = localStorage.getItem("dashboard_layout");
    return saved === "1" ? "1" : "2";
  });

  const updateMode = useCallback((next: LayoutMode) => {
    localStorage.setItem("dashboard_layout", next);
    setMode(next);
  }, []);

  return [mode, updateMode] as const;
}
