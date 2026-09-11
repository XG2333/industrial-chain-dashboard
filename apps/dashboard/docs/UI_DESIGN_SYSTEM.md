# 每日市场监测 AI 看板 UI Design System

本文件是 Dashboard 的统一 UI 规范。新增或改造页面时，必须优先遵循本规范，并使用项目级共享组件，而不是在页面里散落重复样式。

## 1. UI Framework

- UI Framework：Flowbite React，作为 React 19 + Tailwind CSS 3.4 之上的组件层。
- 路由：React Router 7；图标：Phase 1 继续使用 lucide-react，图标统一决策放到 Phase 3。
- 图表：ECharts 5.5；本阶段及后续改造均不得修改数据计算、分组、排序、清洗逻辑。
- 禁止为 UI 改造升级 React、Vite、Tailwind、React Router、ECharts 或 FastAPI。

## 2. Theme Architecture

主题流向必须保持单向：

```text
Flowbite Base Theme
        ↓
Project Theme (frontend/src/theme/flowbiteTheme.ts)
        ↓
Shared Dashboard Components (frontend/src/components/ui/)
        ↓
Pages
```

禁止在页面里对单个 Flowbite Component 反复覆盖主题。页面只能使用共享组件或标准 Flowbite class。

## 3. Color System

设计 Token 定义在 `frontend/src/theme/dashboardTokens.css`，同时保留 `frontend/src/index.css` 中已有变量以兼容旧组件。

| Token | Light | Dark |
| --- | --- | --- |
| `--dashboard-bg` | `#ffffff` | `#0f172a` |
| `--dashboard-surface` | `#ffffff` | `#1e293b` |
| `--dashboard-surface-secondary` | `#f1f5f9` | `#334155` |
| `--dashboard-border` | `#e2e8f0` | `#334155` |
| `--dashboard-text-primary` | `#0f172a` | `#f8fafc` |
| `--dashboard-text-secondary` | `#64748b` | `#94a3b8` |
| `--dashboard-primary` | `#1a56db` | `#3f83f8` |
| `--dashboard-secondary` | `#f1f5f9` | `#1e293b` |
| `--dashboard-positive` | `#dc2626` | `#ef4444` |
| `--dashboard-negative` | `#16a34a` | `#22c55e` |
| `--dashboard-warning` | `#d97706` | `#f59e0b` |
| `--dashboard-info` | `#0e7490` | `#22d3ee` |

`positive` / `negative` 遵循 A 股行情约定：红色代表上涨，绿色代表下跌。

## 4. Typography

| Type | Style |
| --- | --- |
| Page Title | 32-40px，font-weight 700，页面顶部 |
| Section Title | 18-20px，font-weight 600 |
| Card Title | 14px，font-weight 600 |
| KPI Value | 24-30px，font-weight 700，数字等宽对齐 |
| Body | 14px，font-weight 400 |
| Secondary Text | 12px，color 使用 text-secondary |
| Table Text | 12-13px，表头 font-weight 600 |

不使用负 letter-spacing；不根据 viewport 缩放字号。

## 5. Spacing

| Context | Value |
| --- | --- |
| Page padding | 24px |
| Section gap | 24px |
| Card gap | 16px |
| Card padding | 20px |
| Grid spacing | 16px |
| Table row padding | 8-12px |

## 6. Card Specification

- 使用 `DashboardCard` 或 Flowbite `Card`。
- Radius：8px（`rounded-lg`）。
- Border：1px `--dashboard-border`。
- Background：`--dashboard-surface`。
- Shadow：`shadow-sm`；hover 时允许提升为 `shadow-md`。
- 深色模式：`dark:bg-slate-800`，border 使用 slate-700。

## 7. KPI Specification

- KPI 容器使用 Card 样式。
- 指标名使用 Secondary Text。
- 数值使用 KPI Value。
- 涨跌颜色必须使用 `positive` / `negative` Token，不得在页面硬编码 `#ef4444` / `#22c55e`。

## 8. Table Specification

- 优先 Flowbite `Table` 或现有 `IndustryChartTable` 的视觉基线。
- 表头背景 `surface-secondary`，字体 600。
- 行 hover 背景使用 `surface-secondary` 半透明。
- 单元格对齐：数字右对齐，文本左对齐。

## 9. Chart Container Specification

- ECharts 组件本身不改数据逻辑。
- 图表外围容器统一使用 `DashboardCard`：标题、单位、Toolbar、刷新按钮由容器负责。
- Chart 区域保持 `background-color: #fff`，深色模式统一在 Phase 3 处理。

## 10. Button Specification

- 优先 `DashboardButton`（Flowbite `Button`）。
- 默认 `size="sm"`，默认 `color="light"`。
- 主操作使用 Flowbite primary color；次要操作使用 light。
- 图标按钮必须保留 `aria-label` / `title`。

## 11. Icon Specification

- Phase 1 继续使用 lucide-react，不批量替换。
- Flowbite React 自身不要求更换图标体系。
- Phase 3 再决定是否统一为 Flowbite Icons；届时只换图标，不改业务逻辑。

## 12. Layout Specification

- Application Shell 使用 Flowbite `Sidebar` + `Navbar` 构建，入口为 `Layout.tsx`。
- Sidebar 保留 `Overview`、`Tin`、`Silicon`、`Battery` 四个真实路由，使用 lucide-react 图标，支持 Active Route、Hover、Dark Mode 和移动端抽屉行为。
- Header 只保留真实功能：品牌、页面标题、Dark Mode 切换；不在 Phase 2 添加头像、消息、通知、搜索等 Admin 元素。
- 行业页使用统一 `PageHeader` 标题带；Overview 使用完整 `PageHeader` 承载标题、更新时间、Badge 和刷新操作。
- 页面内容最大宽度 1600px，居中布局；禁止 `width: 1370px; left: 425px` 这类固定绝对布局。
- 主内容使用响应式 grid：移动端单列，桌面端按业务密度 2-4 列。

## 13. Responsive Rules

- 最低适配 1920x1080、常见笔记本宽度、浏览器窗口缩放。
- 优先 Tabler 已被替换为 Flowbite 的 Grid：Tailwind CSS Grid + Flowbite 组件。
- 长文本必须可换行或截断，不得溢出容器。
- 按钮、Badge、输入框必须有稳定高度，避免 hover/加载态导致布局跳动。

## 14. New Page Rules

- 新页面必须使用共享组件和 Token，不得在页面内新建重复颜色、间距或组件。
- 新增 Flowbite 组件时，更新 `frontend/scripts/generate-flowbite-classes.mjs` 自动生成的 class list，不手工维护样式清单。
- 新页面数据获取、指标计算、API 契约必须与现有 FastAPI 保持一致。
- UI 改造与业务逻辑修改必须分离；任何数据结果变化都需要先说明原因。
