---
name: 吃什么（what-to-eat）
description: 晚餐决策收口工具——街角灯箱世界：墨绿铁皮底、芥末黄唯一大色块、3px 描边贴纸卡、可换"灯箱片"主题，零渐变零柔光
colors:
  # ── 片 evening 晚市（默认片，暗色第一公民）──
  evening-bg-0: "#0F1F18"
  evening-bg-1: "#14281F"
  evening-bg-2: "#1B3327"
  evening-bg-3: "#24402F"
  evening-ink-1: "#F2EFE6"
  evening-ink-2: "#A8B5A3"
  evening-ink-3: "#6E8274"
  evening-y: "#FFC53D"
  evening-y-ink: "#101A14"
  evening-r: "#FF5A3C"
  evening-r-text: "#FF8A6E"
  evening-c: "#3DDAD7"
  evening-line: "#2A4436"
  evening-focus: "#3DDAD7"
  evening-sticker-bd: "#FFC53D"
  # ── 片 late 深夜（钠灯）──
  late-bg-0: "#0B1411"
  late-bg-1: "#10201A"
  late-bg-2: "#15291F"
  late-bg-3: "#1D3527"
  late-ink-1: "#EFEAD9"
  late-ink-2: "#9FAE9A"
  late-ink-3: "#5F7367"
  late-y: "#FFA53C"
  late-y-ink: "#141007"
  late-r: "#F0644A"
  late-r-text: "#FF8A6E"
  late-c: "#2FA39B"
  late-line: "#24382E"
  late-focus: "#2FA39B"
  late-sticker-bd: "#FFA53C"
  # ── 片 morning 清晨（亮，豆浆纸白）──
  morning-bg-0: "#F5F1E6"
  morning-bg-1: "#FBF8EF"
  morning-bg-2: "#EFE9D8"
  morning-bg-3: "#E6DFC9"
  morning-ink-1: "#1A241E"
  morning-ink-2: "#4C5A50"
  morning-ink-3: "#8A968C"
  morning-y: "#D98E04"
  morning-y-ink: "#1A241E"
  morning-r: "#B33018"
  morning-r-text: "#B33018"
  morning-c: "#0E8F88"
  morning-line: "#D8D0B8"
  morning-focus: "#0E8F88"
  morning-sticker-bd: "#1F4A38"
  # ── 片 noon 午市（亮，白炽豆绿；--y 即墨绿大色块）──
  noon-bg-0: "#EFF2E4"
  noon-bg-1: "#F8FAEF"
  noon-bg-2: "#E6EAD6"
  noon-bg-3: "#DBE1C6"
  noon-ink-1: "#182420"
  noon-ink-2: "#44544A"
  noon-ink-3: "#7E8D82"
  noon-y: "#1F4A38"
  noon-y-ink: "#F2EFE6"
  noon-r: "#C93A22"
  noon-r-text: "#B33018"
  noon-c: "#0E8F88"
  noon-line: "#D2D8BE"
  noon-focus: "#0E8F88"
  noon-sticker-bd: "#1F4A38"
typography:
  dish:
    fontFamily: "-apple-system, 'PingFang SC', 'HarmonyOS Sans SC', 'MiSans', 'Source Han Sans SC', 'Noto Sans CJK SC', 'Microsoft YaHei', sans-serif"
    fontSize: "40px"
    fontWeight: 900
    lineHeight: 1.15
    letterSpacing: "0.01em"
  slogan:
    fontFamily: "-apple-system, 'PingFang SC', 'HarmonyOS Sans SC', 'MiSans', 'Source Han Sans SC', 'Noto Sans CJK SC', 'Microsoft YaHei', sans-serif"
    fontSize: "26px"
    fontWeight: 900
    lineHeight: 1.3
    letterSpacing: "0.02em"
  heading:
    fontFamily: "-apple-system, 'PingFang SC', 'HarmonyOS Sans SC', 'MiSans', 'Source Han Sans SC', 'Noto Sans CJK SC', 'Microsoft YaHei', sans-serif"
    fontSize: "20px"
    fontWeight: 900
    lineHeight: 1.4
    letterSpacing: "normal"
  body:
    fontFamily: "-apple-system, 'PingFang SC', 'HarmonyOS Sans SC', 'MiSans', 'Source Han Sans SC', 'Noto Sans CJK SC', 'Microsoft YaHei', sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  caption:
    fontFamily: "-apple-system, 'PingFang SC', 'HarmonyOS Sans SC', 'MiSans', 'Source Han Sans SC', 'Noto Sans CJK SC', 'Microsoft YaHei', sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  button:
    fontFamily: "-apple-system, 'PingFang SC', 'HarmonyOS Sans SC', 'MiSans', 'Source Han Sans SC', 'Noto Sans CJK SC', 'Microsoft YaHei', sans-serif"
    fontSize: "17px"
    fontWeight: 900
    lineHeight: 1.2
    letterSpacing: "0.08em"
  mono-num:
    fontFamily: "ui-monospace, 'SF Mono', Menlo, Consolas, monospace"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
    fontFeature: "tabular-nums"
rounded:
  card: "12px"
  button: "12px"
  pill: "999px"
  lightbar: "8px"
  toast: "10px"
spacing:
  s-2: "8px"
  s-3: "12px"
  s-4: "16px"
  s-5: "20px"
  s-6: "24px"
  s-8: "32px"
components:
  button-primary:
    backgroundColor: "{colors.evening-y}"
    textColor: "{colors.evening-y-ink}"
    typography: "{typography.button}"
    rounded: "{rounded.button}"
    height: "52px"
    width: "100%"
    padding: "0 16px"
  button-primary-disabled:
    backgroundColor: "{colors.evening-y}"
    textColor: "{colors.evening-y-ink}"
    typography: "{typography.button}"
    rounded: "{rounded.button}"
    height: "52px"
    width: "100%"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.evening-ink-1}"
    typography: "{typography.caption}"
    rounded: "{rounded.button}"
    height: "52px"
    width: "100%"
  tag-chip:
    backgroundColor: "transparent"
    textColor: "{colors.evening-ink-1}"
    typography: "{typography.caption}"
    rounded: "{rounded.pill}"
    height: "44px"
    padding: "8px 16px"
  tag-chip-selected:
    backgroundColor: "{colors.evening-y}"
    textColor: "{colors.evening-y-ink}"
    typography: "{typography.caption}"
    rounded: "{rounded.pill}"
    height: "44px"
    padding: "8px 16px"
  option-row:
    backgroundColor: "{colors.evening-bg-1}"
    textColor: "{colors.evening-ink-1}"
    typography: "{typography.body}"
    rounded: "{rounded.button}"
    height: "52px"
    width: "100%"
    padding: "12px 16px"
  sticker-card:
    backgroundColor: "{colors.evening-bg-1}"
    textColor: "{colors.evening-ink-1}"
    rounded: "{rounded.card}"
    padding: "24px 20px"
  lightbar:
    backgroundColor: "{colors.evening-y}"
    textColor: "{colors.evening-y-ink}"
    typography: "{typography.caption}"
    rounded: "{rounded.lightbar}"
    padding: "6px 12px"
    width: "max-content"
  sheet:
    backgroundColor: "{colors.evening-bg-1}"
    textColor: "{colors.evening-ink-1}"
    rounded: "12px 12px 0 0"
    padding: "24px 20px"
    width: "100%"
  toast:
    backgroundColor: "{colors.evening-bg-1}"
    textColor: "{colors.evening-ink-1}"
    rounded: "{rounded.toast}"
    padding: "10px 16px"
    width: "88vw"
---

# Design System: 吃什么（街角灯箱）

## Overview

**Creative North Star: "街角灯箱"——深夜街角的一块灯箱，热闹，但一次只亮一块牌子。**

本系统记录的是已建成的高保真原型（`docs/design/hifi/index.html`，单一 HTML 文件、零框架、零 Webfont、CSS-only 动效）中实际落地的视觉规则；凡规格（`docs/design/design-system.md`）与实现不一致处，以实现为准。世界的根隐喻来自拍板方向 C：一块大排档灯箱——单屏单焦点，一屏只做一个决定。界面拒绝品类默认的"卡片列表＋渐变英雄区"，也拒绝把推荐做成信息流。

系统是两层的：**结构层永不换**（贴纸 3px 描边、12px 圆角、硬阴影厚度、翻牌动效、系统标语体、一块牌子的色彩纪律），**片层可换**（`html[data-theme]` 切换的四张"灯箱片"：晚市/深夜为暗色片，清晨/午市为亮色片；`html[data-season]` 用 `color-mix` 微调地面温度）。主题切换是 60ms 直切的"啪"，不做渐变过渡——灯箱换片就是换片。

密度是工具级的：单列、大按钮、一句推荐语、常驻兜底出口。热闹感只投放在三个品牌时刻（首屏承接、翻牌揭晓、回访闭环），其余屏克制。立体感只来自描边与位移，从不来自光影渲染。

> 证据分级：finish review 已以 16 张真机截屏（`.impeccable/review/01–16`）收口为 disposition:ship（一轮修复＋一轮重捕）。其中三处动效——翻牌 240ms 过冲、灯箱点亮 60ms、等待卡描边呼吸——为代码验证、未经逐帧真机捕获，下文均已标注。

**Key Characteristics:**
- 两层 token：结构层（描边/圆角/阴影/字级/动效）不变，片层（`data-theme` 色彩变量组）可换
- 芥末黄（片主色）是唯一可做大色块的颜色；红/青只做文字级点缀与细线
- 零渐变、零柔光、零 text-shadow；厚度＝`0 4px 0` 硬偏移阴影＋3px 描边
- 系统黑体 w900 标语体＋等宽 tabular 数字（票据角标感），零 Webfont
- 选中/换片/点亮全是 60ms 硬填充直切，无渐隐
- 触达 ≥44px，主行动 52px 且位于拇指热区，兜底出口常驻

## Colors

四张"灯箱片"共享同一套语义变量名；每片一组完整取值，切换靠 `data-theme` 属性。暗色片（evening/late）是默认与最打磨路径；亮色片（morning/noon）由同一套纪律约束。地面有四级层次（bg-0 地面 → bg-1 卡面 → bg-2 按压反馈面 → bg-3 点亮闪帧色），文字三级墨色。

### Primary
- **片主色 --y（每片唯一大色块）**：晚市芥末黄 `#FFC53D`、深夜钠灯橙 `#FFA53C`、清晨现炸金 `#D98E04`、午市铁皮墨绿 `#1F4A38`（frontmatter 键 `*-y`）。用于：主按钮底、灯箱判定牌（lightbar）底、选中标签/选项的填充、结果卡剪影、`::selection`。它承载每屏唯一的"亮牌"。
- **牌上字 --y-ink（`*-y-ink`）**：主色底上的文字/描边色，随片配对（晚市 `#101A14`、深夜 `#141007`、清晨 `#1A241E`、午市纸白 `#F2EFE6`）。
- **贴纸描边 --sticker-bd（`*-sticker-bd`）**：主卡片 3px 描边用色。暗色片＝片主色（黄/橙描边），亮色片＝深墨绿 `#1F4A38`（黄在纸白底上不达标，描边交给墨绿）。

### Secondary
- **辣椒红 --r（`*-r`）与提亮红字 --r-text（`*-r-text`）**：负反馈/耗尽/错误的限量点缀。**实现现状**：已建界面实际只消费 `--r-text`（负反馈链接、降级角标"家常兜底版"、行内错误）；`--r` 原色在构建中定义但未被任何规则引用——它是纪律预留位（≥20px w900 或图形场景），不是已用色。

### Tertiary
- **荧光青 --c／焦点青 --focus（`*-c`／`*-focus`）**：只做 2–3px 细线与焦点环。**实现现状**：青色进入界面的唯一通道是 `--focus`（`:focus-visible` 2px 环）；`--c` 变量本身当前无直接消费者（细线/success 预留）。暗色片为亮青（`#3DDAD7`／深夜 `#2FA39B`），亮色片为深青 `#0E8F88`。

### Neutral
- **地面四级 `*-bg-0..3`**：bg-0 页面地面（晚市墨绿铁皮 `#0F1F18`）；bg-1 卡片/弹层/ Toast 面；bg-2 按压反馈面（ghost 按下、原型 chip 按下）；bg-3 只有一个消费者——揭晓瞬间的"灯箱点亮"60ms 闪帧（JS 置卡底为 bg-3 再还原）。
- **墨色三级 `*-ink-1..3`**：ink-1 主文字（暗片纸白、亮片墨绿黑）；ink-2 次文字/注释（caption、票号、图标灰绿）；ink-3 当前唯一消费者是原型控制台 summary——**它不是产品文字色，不要用于产品 UI**。
- **中性描边 `*-line`**：2px 次级描边（ghost 按钮、标签、选项、虚线分隔）的全部用色。

### 季节调制（副轴）
`data-season` 只覆写一件事：地面 bg-0 用 `color-mix(in oklab, var(--bg-0-base) N%, 调色)`——春 94% 混 `#3DDAD7`、夏 95% 混 `#2FA39B`、秋 93% 混 `#D98E04`、冬 96% 混 `#5A6B70`。不支持 `color-mix` 的内核回退 base 地面。主色、墨色、结构一概不动。（规格曾写"调制三个地面变量＋点缀降饱和"，实现只动了 bg-0——以实现为准。）

### 换片机制（实现的真相）
本地时钟自动换片（零网络零定位）：`<5h` 深夜、`5–9h` 清晨、`10–16h` 午市、`17–20h` 晚市、`≥21h` 深夜；季节按月份 12–2 冬／3–5 春／6–8 夏／9–11 秋。手动覆盖存 `wte_theme`／`wte_season`（身份页点选），"跟随时间/季节"即删键回归自动。

### Named Rules
**「一次只亮一块牌子」Rule。** 每屏只承载一个决定、一个主行动；片主色是唯一可做大色块的颜色，红/青永不填充面积。灯箱可以换片，不能满堂彩。

**平涂 Rule（零渐变零柔光）。** 一切表面是实色平涂：无渐变、无 blur 阴影、无发光、无 text-shadow。立体感只来自描边（3px/2px）与位移（硬偏移阴影）。

**结构不变，片子换 Rule。** 新主题只允许换 `data-theme` 下的颜色变量组；描边宽度、圆角、阴影、字级、动效时长是结构层，任何片都不得改写。

## Typography

**Display/Body Font:** 系统黑体栈 `-apple-system, "PingFang SC", "HarmonyOS Sans SC", "MiSans", "Source Han Sans SC", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif`（零 Webfont，首屏 ≤2s 硬预算的硬前提）
**Label/Mono Font:** `ui-monospace, "SF Mono", Menlo, Consolas, monospace`（`.num` 类，加 `font-variant-numeric: tabular-nums`）

**Character:** 招牌吆喝感——强调全靠字重 900 与字距，不靠装饰。菜名是海报，标语是灯箱字，等宽数字是票据角标；正文保持 16px/1.6 的低负担可读性（暗光单手持机场景）。

### Hierarchy
- **菜名 Display**（w900, 40px/1.15, 字距 .01em, `overflow-wrap: anywhere`）：结果揭晓主视觉、兜底菜名。次级屏inline降档：弃答 34px、跳转过场 30px、兜底页 28px。
- **标语 Slogan**（w900, 26px/1.3, 字距 .02em）：首屏「今晚它说了算。」；等待屏复用为 22px。
- **题干 Heading**（w900, 20px/1.4）：问卷/画像题干；卡内次级标题 inline 降为 17–18px。
- **正文 Body**（w400, 16px/1.6）：推荐语、隐私条款、说明。
- **按钮字**（w900, 17px, 字距 .08em）：主按钮标语体；ghost 按钮 w500 15px。
- **判定牌字**（w900, 15px, 字距 .06em）：lightbar。
- **注释 Caption**（w400, 13px/1.5, ink-2）：预算说明、免责、指引；错误/负反馈文字用 13px w500 `--r-text`（`.cap-r`/`.linklike`，下划线 offset 3px）。
- **票号/数字 Mono**（`.num`，12px 票头–28px 秒表均见）：步数、秒数、剩余次数、日期编号、anon 标识。全部 tabular-nums。

### Named Rules
**系统字 w900 Rule。** 强调只允许"字重 900＋字距"，禁止 text-shadow 描字、禁止引入 Webfont、禁止用细体放大冒充标语体。

**Mono 票据 Rule。** 一切计数、计时、编号、日期必须走 `.num`（等宽＋tabular-nums）——预算感是这个产品的视觉语言，不许用比例数字。

## Layout

手机单列流式布局：`body` 内边距 20px（--s-5），视口 ≥460px 时内容收为 `max-width: 420px` 居中（桌面即居中手机列）。无断点阶梯、无网格——只有一列与垂直节奏。

**间距节奏（实现值）**：App 级区块间距 24px（--s-6）；视图内块与块之间 20px（--s-5，`.stack-l`）；紧凑组内（选项组、标签墙 gap）12px（--s-3，`.stack`）。可选步长 8/12/16/20/24/32 六档（--s-2..s-6＋s-8）。✅ 缺陷修复存档（已解决，2026-09-03 文档化后）：等待屏内联样式的 `var(--s-8)` 曾引用未定义 token，现已在 `:root` 补上 `--s-8:32px`（等待卡内边距恢复预期 32px/20px，无其他受影响面）；--s-1/--s-10 仍不存在，禁止引用。

**拇指热区**：主行动是 100% 宽 52px 按钮，位于内容流末尾（首屏即拇指热区）；常驻兜底出口（ghost）紧随其下，永不隐藏。双按钮行 `.row2` 对半分，gap 12px。

**触达**：一切可点目标 ≥44px（主/ghost/选项 52px，标签 44px＋`::after inset:-6px` 额外命中垫，票头/链接钮 44px）。

**浮层与安全区**：底部弹层贴底、`padding-bottom: calc(24px + env(safe-area-inset-bottom))`；Toast 固定 `bottom: 88px` 居中、`max-width: 88vw`；`viewport-fit=cover`。跳转过场屏 `padding-top: 30vh` 垂直偏上居中。

## Elevation & Depth

深度是"平涂＋硬位移"体系，不是光影体系。**零 blur 阴影、零渐变、零发光**——层次由三种手段构成：① 色调分层（bg-0 地面 → bg-1 卡面 → bg-2 按压面）；② 硬偏移阴影（贴纸厚度，见下）；③ 描边（3px 主贴纸 / 2px 次级）。遮罩是唯一的大面积压暗：弹层背景 `rgba(6,12,9,.6)`。z 序：弹层遮罩 40，Toast 60。

### Shadow Vocabulary
- **shadow-pop（贴纸厚度）**（`box-shadow: 0 4px 0 rgba(0,0,0,.5)`）：卡片、主按钮、Toast 的常态厚度。注意：实现中该值不随片切换（各片定义的 `--shade` 变量目前未被消费，阴影恒为黑 50%）——亮色片上同样是黑硬阴影，这是已建事实。
- **shadow-press（按压厚度）**（`box-shadow: 0 1px 0 rgba(0,0,0,.5)`）：与 `translateY(3px)` 配合，物理"按下去"。

### Named Rules
**硬阴影即厚度 Rule。** 阴影只有 `0 4px 0` 与 `0 1px 0` 两档，永不加 blur、永不随悬停涨大；厚度变化只能由按压位移触发。

## Shapes

贴纸语言。**圆角**：卡片与按钮 12px（中圆角"贴纸"），标签胶囊 999px，判定牌 8px，Toast 10px，焦点环 4px；底部弹层只圆上两角（`12px 12px 0 0`）且无下描边。**描边**：主贴纸 3px 实色（`--sticker-bd`，暗片=片主色、亮片=墨绿），一切次级元素 2px `--line`；分隔线是 2px 虚线（`border-top: 2px dashed var(--line)`）。**铆钉**：每张贴纸卡四角 5px 圆点（`--line` 色，内缩 7px）——铁皮的极简符号，不做拟物。**图形**：图标一律内联单色 stroke SVG（`stroke: currentColor`，宽 2–2.4，如判定牌 18px 图标）；全系统唯一授权插画位是结果卡尾右下的单色 `--y` 平涂灯箱剪影（48×34，一屏至多一幅，不与判定牌争焦）。

## Components

### 主按钮（BtnPrimary）
- **Shape:** 12px 圆角、100% 宽、`min-height: 52px`、3px `--y-ink` 描边
- **Primary:** 片主色底 `--y` ＋ `--y-ink` 字（w900 17px 字距 .08em）＋ `shadow-pop`
- **Hover / Active:** 按压 `translateY(3px)`＋阴影缩至 `0 1px 0`（90ms `--t-press`）；无 hover 态（触屏世界）
- **Disabled:** `opacity: .45`＋`pointer-events: none`（换一耗尽、未作答的"下一步"）
- **变体语义:** 亮色片上 `--y` 本身换色（清晨金/午市墨绿），纪律不变：主色底＋配对暗字

### Ghost 按钮（次级/兜底）
- **Shape:** 12px 圆角、100% 宽、52px、2px `--line` 描边、透明底
- **Style:** `--ink-1` 字 w500 15px；按压 `translateY(2px)`＋底变 `--bg-2`；disabled `opacity: .4`
- **角色:** 兜底出口、次级动作——永不与主按钮争夺视线

### 标签 Chip（TagChip）
- **Style:** 999px 胶囊、2px `--line`、透明底、15px w500、视觉高 44px＋`::after inset:-6px` 命中垫
- **State:** 选中（`aria-pressed="true"`）＝`--y` 底＋`--y-ink` 字＋边框同色＋w900，**60ms `--t-lit` 硬填充直切，无渐隐无缩放**——灯泡"啪"地亮
- **场景:** 多选口味标签、单选回访反馈、主题换片槽位（同一组件三种语义）

### 选项行（Opt，画像/问卷单选）
- **Style:** 100% 宽左对齐、2px `--line`、12px 圆角、`--bg-1` 底、16px、52px、`padding: 12px 16px`
- **State:** 选中同标签的黄填充直切＋w900；`transition` 含 font-weight（字重跳变即反馈的一部分）

### 贴纸卡（StickerCard）
- **Corner Style:** 12px
- **Background:** `--bg-1`
- **Shadow Strategy:** `shadow-pop`（见 Elevation）
- **Border:** 3px `--sticker-bd` ＋四角铆钉点
- **Internal Padding:** 24px 上下 × 20px 左右（--s-6 / --s-5）

### 判定牌（Lightbar）——签名组件
卡顶的片主色小牌子（8px 圆角、`padding: 6px 12px`、`width: max-content`、w900 15px 字距 .06em，可带 18px stroke SVG 图标）。它**不是 kicker/眉题**——它是判定语本身（「今晚就它」「不选了，直接上菜」「通道维护中」）。本世界没有眉题这个物种；凡是"结论"，就做成灯箱牌。

### 底部弹层（Sheet）与 Toast
- **Sheet:** 贴底全宽（≤420px 居中）、`--bg-1`、3px 描边无下边、上圆角、`slideup 200ms ease-out` 自 40% 上滑；遮罩 `rgba(6,12,9,.6)`
- **Toast:** 底部 88px 居中、`--bg-1` 底＋2px `--sticker-bd`、10px 圆角、14px 字、`shadow-pop`，2.2s 自动消失；用于 429 限流、换一耗尽、复制成功

### 揭晓动效（结果卡，品牌时刻）
顺序＝灯箱点亮 60ms（JS 置卡底 bg-1→bg-3 一次直切；`data-motion="off"` 时直出）→ 翻牌 `rotateX 92°→0` 240ms `cubic-bezier(.2,.7,.3,1.12)` 尾段过冲（transform-origin 50% 0；code-verified only）→ 剪影随卡显现。等待屏：描边呼吸动画（`breathe 1.2s ease-in-out infinite`，`--sticker-bd`↔`--line`，code-verified only）＋ mono 秒表静态数字刷新（100ms 步进，文字非动画）。`prefers-reduced-motion` 下所有 animation/transition 归零、JS 跳过点亮直出终态。

### 焦点与选区
`:focus-visible`＝2px `--focus` 环、offset 2px、4px 圆角（青色系，随片）；`::selection`＝片主色底＋`--y-ink` 字。结果菜名 `aria-live="polite"` 播报。

## Do's and Don'ts

### Do:
- **Do** 只引用语义变量（`var(--y)`、`var(--bg-1)`…）写新屏；颜色永远由 `data-theme` 片层供给，禁止硬编码 hex——唯一例外是季节地面 `color-mix`。
- **Do** 每屏只放一个片主色大色块（主按钮或判定牌），主行动 52px 置拇指热区，兜底 ghost 出口常驻可见。
- **Do** 一切选中/换片反馈用 60ms `--t-lit` 硬填充＋w900，像灯泡"啪"地亮；按压用 `translateY`＋阴影变薄。
- **Do** 一切数字（秒表、剩余次数、步数、编号）用 `.num` mono tabular。
- **Do** 新图标用内联单色 stroke SVG（`currentColor`，2–2.4px）；新插画只允许结果卡尾的单色平涂剪影位，一屏 ≤1 幅。
- **Do** 触达 ≥44px（标签另加 -6px 命中垫）；焦点环 2px `--focus` offset 2px 不被描边吞没。
- **Do** 尊重 `prefers-reduced-motion`：动画归零、保留终态，秒表用静态文字刷新。

### Don't:
- **Don't** 使用渐变、blur/柔光阴影、发光、text-shadow——本世界立体感只来自描边与位移，违者即出戏。
- **Don't** 让红或青填充面积：红每屏至多一处文字级点缀（实现只消费 `--r-text`），青只走细线与焦点环。
- **Don't** 为新主题改结构层：描边宽度、圆角、阴影、字级、动效时长不随片变；换片只换 `data-theme` 颜色组。
- **Don't** 引入 Webfont、UI 组件库脸、emoji/图标字体；强调只用 w900＋字距。
- **Don't** 把 `--ink-3` 用于产品文字（它目前只服务原型控制台）；正文最小 13px 且只用于 caption 层。
- **Don't** 做报错脸：兜底/维护页不加警告三角、不加红底——灯箱坏了灯还是暖的（S9 已建先例）。
- **Don't** 为"多逛"开视觉旁路：换一耗尽＝禁用＋收口文案＋mono 计数到顶，不出现"再来一次"的诱导入口。
- **Don't** 引用未定义的间距步长（--s-1/--s-10 仍未定义；等待屏曾引用未定义的 `var(--s-8)`，该历史缺陷已于文档化后 2026-09-03 在 `:root` 补 `--s-8:32px` 解决）。
