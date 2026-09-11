import * as echarts from "echarts/core";

// 打印修复: echarts 的 canvas 在 init 时尺寸固定, 打印时页面宽度重排(A4/自定义纸张)
// 导致 canvas 与容器错位(图"变乱、与背景框分离")。beforeprint 时对所有活动实例
// 强制 resize, 使 canvas 跟随打印布局; afterprint 恢复屏幕尺寸。
export function initPrintChartResize(): void {
  if (typeof window === "undefined") return;
  const resizeAll = () => {
    const els = document.querySelectorAll<HTMLElement>("[_echarts_instance_]");
    els.forEach((el) => {
      try {
        echarts.getInstanceByDom(el)?.resize();
      } catch {
        /* ignore single chart failure */
      }
    });
  };
  window.addEventListener("beforeprint", resizeAll);
  window.addEventListener("afterprint", resizeAll);
}
