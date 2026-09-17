# 设计红队评审（Stage 5 / design-review）

> 评审对象：`docs/design/design-system.md`（stage 3 规格）＋ `docs/design/hifi/index.html`（stage 4 高保真，Impeccable 终审 disposition: ship 后版本）＋ 真机证据 `.impeccable/review/01–16`
> 评审体：创意总监 / UX 研究员 / 前端工程师 / 无障碍审查者（四角色独立过稿）
> stage_4 自检结果并入：detector 2 warnings（翻牌回摆＝已拍板世界语言，保留；间距节奏＝已修 #app gap）＋ finish review 一轮 fix（5 条）＋一轮 recapture（3 条）→ ship。全程真实载体（Android 真机 Chrome）截图验证。

---

## 逐角色意见表

| 角色 | 位置 | 严重度 | 问题 | 要求的修改 |
|---|---|---|---|---|
| UX 研究员 | S6 结果页「这推荐不行」 | **[重要]** | 负反馈按钮紧贴主按钮下方、13px 居中 linklike——低能量单手场景误触概率最高，而误触直接写记忆层 −1（FR-09），污染推荐数据并违背护栏 2「打扰 ≤10%」的口径精神 | 与「就吃这个」行距拉开至 ≥24px，或右对齐收窄＋二次确认态（现有"记住了"文案保留） |
| UX 研究员 | §1.6 亮色片 --line | **[重要]** | morning/noon 片描边 #D8D0B8/#D2D8BE 对纸白底仅 ~1.35:1——正午户外强光下 ghost 按钮与卡片边界几乎不可见，可点性全靠文字撑；暗光适配是第一公民，但亮色片是拍板理由（白天使用）的正场 | 亮色片 --line 加深至对 bg-0 ≥3:1（非文字元素标准），如 #B8AE8F/#A8B09A |
| 创意总监 | §1.6 换片机制 | **[重要]** | 拍板理由的核心是"主题跟随时间/季节被感知"，但自动换片（含打开页面时片已不同）无任何可感知瞬间——用户永远不知道灯箱换了片，需求等于没落地；换片也不埋点（正确，非用户行为），更无从验证感知 | 首屏灯箱条在片变更后的首次进入给一次 60ms 微闪（reduced-motion 直出）；M1 观察是否需要文案化（如 caption 显示当前片名「晚市 · 秋」） |
| 前端工程师 | index.html :root | **[重要]**（已修·留痕） | `--s-8` 被等待卡 padding 引用但未定义——整个 padding 声明失效（documenter 抓出） | 已修：`:root` 补 `--s-8:32px`；DESIGN.md 缺陷记录同步标记 resolved |
| 前端工程师 | head meta color-scheme | **[重要]** | `color-scheme: dark light` 为静态——noon/morning 片下 UA 控件（原生输入框、滚动条、自动填充样式）仍按暗色渲染；生产 S10 口令输入框将出现"纸白卡上一块黑输入框" | 换片时同步 `document.documentElement.style.colorScheme`（dark 片=dark，light 片=light）；原型无输入框未暴露，属生产必改项 |
| 无障碍审查者 | show() 视图切换 | **[重要]** | 视图切换（S2→S4→S6…）无焦点管理——读屏用户停留原地，新视图内容不进入可达性树焦点流；`aria-live` 只覆盖菜名一处 | show() 后将焦点移至新视图首个标题（tabindex="-1"），或对新视图容器加 `aria-live="polite"` 区域声明；写入阶段 5b 修订与生产实现说明 |
| UX 研究员 | S5 等待态秒表 | [建议] | mono 秒表 0.0s→1.4s 实时跳字：对决策耗竭用户是"倒计时压力"（时间在流逝），与收口安心感相反；P95 ≤3s 内只跳三下，信息价值趋零 | 改静态「翻牌中——好菜不过夜。」，秒数移入 caption 或删除 |
| 创意总监 | S2 vs S4 弃答文案 | [建议] | 同一出口两种口癖：「懒得选？翻牌直给」（S2）vs「不想选了，直接给」（S4）——人格统一但措辞双轨 | 统一为"翻牌直给"家族（S4 改「不想选了？翻牌直给」），文案规格表同步 |
| 创意总监 | S6 揭晓剪影 | [建议] | 平涂剪影是一只"通用碗"——汤与烤鱼同碗，记忆点打折；灯箱招牌本就象征化，可接受 | 登记设计债：菜类目→剪影映射（汤/饭/面/烤四型），触发条件＝M1 首推接受率数据回流后评估 |
| 无障碍审查者 | :root --ink-3 / --r / --c / --shade | [建议] | 四个 token 定义未消费（documenter 已记）——--ink-3 对 bg-0 仅 ~3.4:1，留着即误用 invite | 删除或注释"禁用于 <18px 文字"；生产实现时以 lint 规则守 |
| 无障碍审查者 | S5 秒表 JS timer | [建议] | reduced-motion 只关了 CSS 动画；秒表是 JS 文字更新（未加 aria-live，读屏不播报 ✓，视觉上仍是"动"） | 与 UX #秒表条合并处置 |

## 专项清单穷尽核对（规则 2：逐项给结论，不允许宣布找不出）

| 清单项 | 结论 |
|---|---|
| AI 味八特征 | 无命中：无蓝紫渐变/默认 Tailwind/SaaS 脸/衬线×无衬线套路/emoji 图标/低对比灰字（fix 轮已修两处真对比度违约）/无意义浮动/装饰渐变（全站零渐变）；kicker 禁令的辩护成立（判定语牌子，评审已确认） |
| 暗光不适配 | 无：暗色第一公民＋四片体系；风险在亮色片户外（见 UX #2 [重要]） |
| 触达区过小 | 无：主按钮 52px、标签 44px 命中垫；负反馈为误触风险而非不可达（见 UX #1） |
| reduced-motion | 无：CSS 全关＋JS 点亮/翻牌带 data-motion 守卫；残留 JS 秒表（[建议]） |
| 四态缺失 | 无：13 屏四态在规格 §二全定义；原型已证 10 态，S5/S8 证据为静态定格（评审接受）；**生产实现时 S4 的 429 态与 S10 锁定态必须真机复验** |
| 品牌时刻无记忆点 | 无：揭晓（判定牌＋剪影＋翻牌）成立；风险＝换片无感知（见 CD #1 [重要]） |
| 文案语气脱离人格 | 无双轨外偏离；口癖统一见 CD #2 [建议] |
| 趣味性违反立场红线 | 无：翻牌/点亮全部 ≤400ms 不阻塞交互；无"再逛逛"路径；换一耗尽禁用态经 fix 轮可视化（.ghost[disabled]） |

## 埋点回归（硬门禁）

FR-15 全类核对通过：点击类 15 个 data-track ＋ 到达类 6 个 track() 存根（session_start/answer/cold_start/abandon/accept/swap/negative_feedback/re_ask/privacy_ack/fakedoor 三事件/visit 双事件/link_dead_fallback/result_served/recommend_exposure/jump/fallback_result）。**设计稿为绿地原型轨，生产代码未触碰——上线替换时按本表逐项回归。**

## 总体判定：**修订后可**

6 条 [重要]（1 条已修留痕）全部指向可通用化原则：数据质量（误触污染记忆）、户外可用性、拍板理由的落地完整性、生产形态差（color-scheme/焦点管理）。方向与世界语言无需重做——判定牌/贴纸/换片体系经终审 ship。

**停机：等待你的处置意见（逐条采纳/驳回）后进入 stage_5b 修订。**

---

## 附：交付物清单

| 阶段 | 文件 |
|---|---|
| 1 语境卡 | `docs/design/design-brief.md`（含拍板后使用环境修订＋G7 未决） |
| 2 方向卡 | `docs/design/design-directions.md`（含拍板记录：C＋理由原文） |
| 3 设计规格 | `docs/design/design-system.md`（含 §1.6 灯箱片主题系统） |
| 4 高保真 | `docs/design/hifi/index.html`（单文件原型）＋ `PRODUCT.md`＋`DESIGN.md`＋`.impeccable/design.json`＋真机证据 `.impeccable/review/01–16` |
| 5 红队 | `docs/design/design-review.md`（本文件） |
