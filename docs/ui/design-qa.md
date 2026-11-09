# DataFusion 界面视觉验收

结果：通过。

- 参考图：`docs/ui/design-reference.png`，原图 2560 × 1383；对照时裁去顶部 80px 浏览器栏，得到 2560 × 1300 的页面区域。
- 实现截图：`docs/ui/design-current-desktop.png`，视口 2560 × 1300；移动端截图：`docs/ui/design-current-mobile.png`，视口 390 × 844。
- 完整对照：`docs/ui/design-comparison.png`；欢迎区局部对照：`docs/ui/design-comparison-focus.png`。完整对照将参考页面与实现截图等比例缩至 1280 × 650 后并排展示。局部对照保留两图的原始像素密度。

## 视觉检查

| 区域 | 检查结果 |
| --- | --- |
| 页面骨架 | 深青色固定侧栏、浅米色主区、顶部状态栏和底部输入框与参考图的层次一致。 |
| 欢迎区 | 绿色文档图标、细字标签、大标题、说明和三张提问卡片均已对齐同一内容宽度。 |
| 色彩与细节 | 奶绿主按钮、浅绿图标底、白色卡片、柔和边框及轻阴影已应用。 |
| 排版 | 大标题、卡片文字和辅助文字建立了清楚的层级；窄屏没有横向溢出。 |
| 内容差异 | 保留 DataFusion 品牌、真实 Chinook/PDF 数据源与运行状态；没有复制参考图中的 404 错误提示或无关教材问题。 |

首轮对照发现欢迎区位置略低、卡片偏矮，随后调整了宽屏垂直留白、卡片高度和文字尺寸。最终重新截取桌面图并复查了完整与局部对照。移动端改为纵向滚动内容与贴底输入区，三张卡片和输入框都可使用。

## 交互与运行检查

- PDF 问答：点击建议问题后返回真实答案、页码引用和执行步骤；点击引用可预览原 PDF 对应页。
- 数据库问数：点击艺术家总数问题后返回 `275`、生成的 SQL、结果表和执行步骤。
- 新建对话、PDF/数据库模式切换正常；浏览器控制台无错误。
- `npm run build` 通过；后端 `python -m pytest tests -q` 为 38 passed。
- 实际运行探测：前端 `/data-agent` 返回 200；后端 `/api/health` 返回 `status: ok`，MySQL、LLM、Vector Store 均为 `true`。

## 后续视觉迭代

参考图只作为清爽布局与配色的方向。根据用户反馈，欢迎区加入了 DataFusion 自己的“当前工作流”卡片，按 PDF RAG 或 MySQL NL2SQL 展示处理步骤；建议问题前增加了清晰的起点提示。PDF 引用卡片则增加文件图标、页码、检索分数和直接的“查看原文”按钮，实际点击可以打开对应 PDF 原页。窄屏把侧栏压成双列顶部导航，首屏可以看到问答内容。

最终桌面与移动端截图分别保存为 `docs/ui/design-refined-desktop.png`、`docs/ui/design-refined-mobile-welcome.png`。这次迭代有意保留参考图的轻盈感，同时使用项目真实的数据源、工作流和引用能力形成独立界面。

## 顶部问答导航

数据库问答和文档问答现在位于工作台顶部，是两个可直接访问的 Vue Router 路由：`/data-agent` 与 `/data-agent/document`。左侧仅负责展示 Chinook 和 PDF 数据源，以及上传/移除文档。已在浏览器验证顶部点击切换、文档路由刷新、后退导航和 390px 窄屏布局；最终桌面截图在 `docs/ui/top-route-document.png`，窄屏截图在 `docs/ui/top-route-mobile.png`。
