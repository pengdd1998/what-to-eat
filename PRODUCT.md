# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

设计原型轨（既有生产前端存在但本任务声明为绿地设计）：静态 HTML/CSS ＋ 原生 JS 单文件原型，零框架、零 Webfont、CSS-only 动效——对齐生产约束（Jinja2 SSR 无 bundle，HC-3）。生产栈＝FastAPI + Jinja2 SSR（impl §1.1）。Init 访谈按任务指令以 `docs/design/design-brief.md`（stage_1 语境卡）为输入替代，未另行提问。

## Users

25–35 岁一二线城市职场人，下班后晚间（核心时段 17:30–21:30）独食晚餐场景；身体状态＝决策耗竭、低能量、单手持机、暗光环境。要做的工作：把"今晚吃什么"这个拖了 10–22 分钟的决定，在 30 秒内交给一个替他拍板的东西。

## Product Purpose

晚餐决策收口工具：≤3 道自适应选择题（≤5 秒/题）→ 唯一结果＋一句情绪化推荐语 →「就吃这个」跳转外卖平台搜索该菜名。成功＝北极星（周活跃人均主动收口次数 ≥1.5）与护栏（首推接受率 ≥50%、耗尽率红线、负向 ≤10%）。

## Positioning

大平台按浏览时长变现、给"更多可逛"；本产品给"就此收口"——≤5 步、唯一答案、记得口味、直达点单。差异化＝交互预算极限＋个人味觉记忆＋成对约束，不拼餐厅数据。

## Operating Context

P-c 载体：微信外手机浏览器直接打开（whattoeat.lifestyle）＋ PWA 安装；微信内 webview 硬拦截（分发话术须指向系统浏览器）。晚间室内/通勤暗光是默认场景 → 暗色为第一公民。移动网络 4G/5G。

## Capabilities and Constraints

- 交互预算：≤30 秒 / ≤5 次点击（硬验收）；首屏 P75 ≤2s；结果生成池 P99 ≤1s / 实时 P95 ≤3s / 硬超时 6s；302 一跳 P50 ≤300ms。
- 换一上限：稳态 2 次 / 冷启动 3 次＋耗尽标记（禁无限浏览红线）；弃答兜底"直接给 1 家"常驻。
- 埋点：FR-15 事件全集为权威（accept+jump 双事件为北极星）。
- 合规：禁健康/减脂表述＋遵医嘱免责；隐私三不（手机号/微信授权/位置）；假门诚实原则。
- 载体形态：Jinja2 SSR＋原生 JS，无 SPA 构建链；动效 CSS 优先。
- 未决：回访探针 UI 形态（G2）、假门锚点 X（G3）、亮色模式交付（G6）。

## Brand Commitments

产品名「吃什么」；人格五关键词：收口者、记得你的老友、麻利、诚实、情绪同伴（出处见 design-brief §二）。视觉方向已拍板：**C「街角灯箱」**（2026-09-03，docs/design/design-directions.md §拍板记录）——墨绿铁皮底、芥末黄唯一大色块、3px 描边贴纸、翻牌动效、平涂灯箱剪影。

## Evidence on Hand

真实菜品库与文案（MiMo PoC-2 逐字留档 `docs/execution/data/m0/poc2-llm-xiaomimimo-v2.5.txt`）；生产埋点口径（impl §2.1 events 表）；用户访谈素材（`docs/product/user-interview-material.md`，假设级 n=1）。无 logo/品牌视觉资产（G1，从零建立）。

## Product Principles

1. 收口高于探索：任何视觉表达不得增加必要步骤或诱导继续逛。
2. 快是人格：动效与等待全部让位于 30 秒总预算。
3. 被记得要可见：记忆层只在回访时刻可见化，平时隐形。
4. 诚实工具感：不装医生、不画饼、数据最小化是视觉立场。
5. 趣味性集中投放：只投三个品牌时刻（揭晓/首屏承接/回访闭环），其余屏克制。

## Accessibility & Inclusion

对比度 ≥4.5:1；触达 ≥44px；prefers-reduced-motion 全尊重；结果播报 aria-live；暗光可读性优先（暗色第一公民）。
