# 手机基金/资产详情：AI控件不遮阅读区

## 范围与定位

基于最新 `origin/main`（9d66326，已含PR34合并0a54dea）在独立修复分支实现。只涉及AI启动/设置入口的布局、缓存版本和对应程序测试，不修改行情、财务、信号、档案数据或其他checkout。

代码实际位置（`page-agent-loader.js`）：
- 桌面 `#rdAiWrap` 固定在右上 `top:72px`。
- ≤640px 手机改为右下，底距 `max(16px, safe-area-inset-bottom)`；AI按钮40px、设置按钮32px、间距8px。
- AI面板打开时已有 `.rd-ai-panel-open` 规则隐藏启动/设置按钮，避免遮住输入区域；设置卡为独立可关闭对话框。

所以不能简单按“全平台右下”假设改全局按钮位置，也不依赖只增加正文末端留白（那仍会在中间滚动位置压住内容）。

## 修复机制

`installArchiveDock()`在且仅在以下条件成立时，把**原来的按钮DOM节点**移入基金/资产详情顶部的普通文档流工具行：

1. 视口≤640px；
2. `pg-research`与`v-detail`真实可见（同时检查hidden属性和hidden类）；
3. `detailPanel`内有`fundArchive`。

该行独立占56px布局高度，位于档案内容之前，AI/设置按钮不再浮在报告、折叠项或横向原表上。手机档案内要使用AI/设置时从详情顶部工具行进入；功能没有删除、禁用或全局隐藏。关闭面板后工具行恢复。其他页面及桌面恢复原来的浮动入口。

- 保留同一按钮节点和事件监听器；切换基金/资产导致`detailPanel`重建时会重新挂接，不产生重复工具行。
- 监听真实详情容器替换与页面显隐，兼容现有`replaceState`不触发hashchange的路径；不监听原表子树或横向滚动。
- AI面板仍由原逻辑控制；打开时工具行跟随原按钮隐藏规则收起，面板本身不被移动或隐藏。设置卡仍在body中，保留打开/关闭行为。
- 工具行左右按安全区域留白；详情正文底部增加`16px + safe-area-inset-bottom`；设置卡在该手机详情场景下考虑top/left/right/bottom安全区域，并提供100vh回退与100dvh高度约束。
- 不修改`.fa-scroll`的本地横向滚动、不预留侵占表格宽度的固定侧栏、不使用overflow:hidden裁切正文。
- `index.html`更新idle loader缓存版本，避免旧脚本继续悬浮遮挡。

## 程序验证（不是视觉验收）

`tests/archive-ai-layout.test.js`新增6项Node VM/轻量DOM契约：
- 手机基金、资产详情，以及idle loader晚于详情加载的情况；
- 退出详情、隐藏页面、切回桌面时恢复原按钮及监听器；
- 基金切资产重建详情后重挂接，幂等、不复制节点；
- AI打开/关闭状态类、设置卡打开/关闭，AI面板不进入工具行；
- 手机安全区域、原表横向滚动不被裁切，观察器不订阅原表子树；
- 非档案页面不受影响、缓存版本生效。

结果：
- 相关测试 `node --test tests/archive-ai-layout.test.js tests/fund-archive.test.js tests/layout-contract.test.js`：31/31通过（另调用Python夹具2/2通过）。
- 完整 `npm test`：114/114通过，0失败。此前两个利差分位断言在本次最新主线数据下均通过；本修复未改这些测试或金融数据，未通过放宽断言造绿。
- `node --check page-agent-loader.js`及新增测试语法检查通过；`git diff --check`通过。

未运行浏览器、Puppeteer/Playwright或用户电脑；DOM状态/样式契约不能证明像素布局已通过。交由主方真实浏览器复查390px基金/资产详情底部折叠项、展开原表横滑、顶部工具行、AI和设置卡开关、安全区域及退出详情后的桌面/其他页面入口。
