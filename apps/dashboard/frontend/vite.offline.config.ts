import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// 离线单文件快照构建: 与主构建同源同配置, 仅合并全部异步 chunk 为单一入口,
// 产物交给 assemble_offline_html.py 内联成单个可 file:// 直开的 HTML。
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    outDir: 'dist-offline',
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        // lazy 路由/图表 chunk 全部并入主 bundle(file:// 下无法加载分片文件)
        inlineDynamicImports: true,
      },
    },
  },
});
