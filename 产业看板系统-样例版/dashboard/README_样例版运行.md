# 产业看板 · 样例版(运行说明 · 与旧版部署一致)

本包 = 完整项目 + **脱敏样例产业数据**(已内置于 `dashboard/data/`):
数值全随机、无 SMM/交易所来源与公司/成分配比明细、无 AI 筛选文本;
个股为演示企业(代码 999xxx,不拉真实行情)。结构(目录 schema/sheet 布局)与真实一致。

## 新电脑运行(只需两个 bat, 无需手动装 Python/Node)
1. 解压本包到任意目录
2. 双击 **`setup.bat`** —— 一键环境:
   自动检测 Python(没有则 winget 自动安装 Python 3.12)→ 创建 .venv → 安装依赖(约 2-4 分钟)
3. 双击 **`run_all.bat`** —— 启动看板并打开 http://127.0.0.1:8000
   (再次启动只需 run_all.bat, setup.bat 检测到 .venv 会跳过安装)

> 前端为已构建产物(dist 随包), 不需要 Node.js; 如需改前端再 npm run build(Node 14+)。

## 可选: 换一批随机样例
双击 `dashboard\generate_sample_data.bat` 重新生成脱敏样例并覆盖 data/ 后重启看板。

## 随包附带: skill 项目(仅代码/技能/示例输入)
包根另有 **`多skill联动/`** 与 **`Selecting skill/`** 两个 skill 项目(不含真实数据产物/
缓存/.env)。它们不与看板启动耦合:看板跑通后,如需运行 skill 流程(处理示例输入),
请阅读各自 README/CLAUDE.md,并在根 .venv 中补充该项目所需依赖后按各自脚本执行。
(看板运行不需要这些 skill。)

## 目录结构(与旧版一致)
```
产业看板系统-样例版/
├─ setup.bat                一键环境(自动装 Python→venv→pip)
├─ run_all.bat              启动看板
└─ dashboard/      看板本体
   ├─ server.py / frontend/dist(已构建) / frontend/src(源码)
   ├─ data/                  脱敏样例 Excel(产业工作簿 + stock_targets/个股)
   └─ gen_sample_package_data.py / generate_sample_data.bat  样例重生成
```

## 数据边界
- data/ 中只有脱敏样例, 无真实产业信息; 个股行情不显示(代码不存在)
- 期货主力/分时/日K = 新浪公开行情(联网时显示); 机构席位与锡公开仓单 = 交易所公开数据(需 akshare)
