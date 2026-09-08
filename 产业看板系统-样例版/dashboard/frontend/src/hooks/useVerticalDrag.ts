import { useCallback, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";

export function useVerticalDrag(initialTop: number, minBottomGap = 60) {
  const [top, setTop] = useState(initialTop);
  const topRef = useRef(initialTop);
  const suppressClickRef = useRef(false);

  const onMouseDown = useCallback((event: ReactMouseEvent) => {
    const startY = event.clientY;
    const startTop = topRef.current;
    let dragged = false;

    const onMove = (moveEvent: MouseEvent) => {
      const maxTop = Math.max(8, window.innerHeight - minBottomGap);
      const next = Math.max(8, Math.min(maxTop, startTop + moveEvent.clientY - startY));
      if (Math.abs(moveEvent.clientY - startY) > 4) {
        moveEvent.preventDefault();
        dragged = true;
      }
      topRef.current = next;
      setTop(next);
    };

    const onUp = () => {
      suppressClickRef.current = dragged;
      window.setTimeout(() => {
        suppressClickRef.current = false;
      }, 80);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }, []);

  const onClickCapture = useCallback((event: ReactMouseEvent) => {
    if (suppressClickRef.current) {
      event.preventDefault();
      event.stopPropagation();
      suppressClickRef.current = false;
    }
  }, []);

  return { top, onMouseDown, onClickCapture };
}
