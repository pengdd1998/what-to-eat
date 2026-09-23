/* 「吃什么」前端（原生 JS，零构建）。
   分层：页面只渲染，业务全走 /api/*。身份＝localStorage 里的 anon_id，每次请求带 X-Anon-Id。
   可访问性：主行动在内容流末尾、触达≥44px、结果菜名 aria-live 播报、prefers-reduced-motion 全尊重。 */
"use strict";
const $ = (id) => document.getElementById(id);

const Anon = {
  get() { return localStorage.getItem("wte_anon") || ""; },
  set(v) { localStorage.setItem("wte_anon", v); },
};

/* ---------- FR-15 埋点（CLIENT_ALLOWED；client_event_id 幂等；失败回队） ---------- */
const pending = [];
function track(type, payload = {}) {
  pending.push({
    client_event_id: "c-" + (crypto.randomUUID ? crypto.randomUUID()
      : "" + Date.now() + Math.random()).replace(/-/g, "").slice(0, 32),
    session_id: "visit_" + Anon.get(),
    type, payload,
  });
  flush();
}
function flush(sync) {
  if (!pending.length) return;
  const batch = pending.splice(0, 50);
  const body = JSON.stringify({ events: batch });
  const headers = { "Content-Type": "application/json", "X-Anon-Id": Anon.get() };
  if (sync && navigator.sendBeacon) {
    navigator.sendBeacon("/api/events/batch", new Blob([body],
      { type: "application/json" }));
    return;
  }
  fetch("/api/events/batch", { method: "POST", headers, body })
    .catch(() => pending.unshift(...batch));
}
addEventListener("pagehide", () => flush(true));

async function api(path, opts = {}) {
  const headers = Object.assign(
    { "Content-Type": "application/json", "X-Anon-Id": Anon.get() },
    opts.headers || {});
  let r;
  try {
    r = await fetch(path, Object.assign({}, opts, { headers }));
  } catch (e) {                       // 断网/超时：返回合成错误，调用方走统一兜底
    return { status: 0, body: {} };
  }
  let body = {};
  try { body = await r.json(); } catch (e) { /* 空响应 */ }
  return { status: r.status, body };
}

/* ---------- 主题：随本地时钟（6:00~18:00 奶油暖色，否则暗夜暖灯），可手动覆盖 ---------- */
function resolvedTheme(mode) {
  if (mode !== "auto") return mode;
  const h = new Date().getHours();
  return (h >= 6 && h < 18) ? "day" : "night";
}
function initTheme() {
  const m = localStorage.getItem("wte_theme_mode") || "auto";
  document.body.dataset.theme = resolvedTheme(m);
}

/* 吸底导航：按当前路径高亮本页 */
(function markNav() {
  const path = location.pathname.replace(/\/$/, "") || "/";
  document.querySelectorAll(".footnav a").forEach((a) => {
    const href = a.getAttribute("href").replace(/\/$/, "") || "/";
    if (href === path) a.setAttribute("aria-current", "page");
  });
})();

/* ---------- 身份：首访 bootstrap + 隐私弹窗 ---------- */
async function bootstrapIdentity() {
  let { status, body } = await api("/api/identity/bootstrap", { method: "POST" });
  if (status !== 200) {                    // 网络抖动重试一次（首访失败＝全功能不可用）
    await new Promise((r) => setTimeout(r, 600));
    ({ status, body } = await api("/api/identity/bootstrap", { method: "POST" }));
  }
  if (body.anon_id) Anon.set(body.anon_id);
  return body;
}

/* 换片计数渲染（P0-1）：剩 n 递减，耗尽打烊 */
function renderSwapCounter(left) {
  const btn = $("btn-again");
  if (!btn) return;
  if (typeof left === "number" && left > 0) {
    btn.disabled = false;
    btn.textContent = "换一个（剩 " + left + "）";
  } else if (left === 0) {
    btn.disabled = true;
    btn.textContent = "换一个（今天用完了）";
  }
  $("btn-accept") && ($("btn-accept").disabled = false);
}

/* 兜底：任何 API 异常都回到开始屏并提示，禁止静默白屏（真机事故 2026-09-15） */
function quizFail(msg) {
  ["screen-quiz", "screen-wait", "screen-result"].forEach((id) => hide($(id)));
  show($("screen-start"));
  const hint = $("taste-hint");
  if (hint) hint.textContent = msg || "网络开小差了，请再试一次";
}

/* FR-16/17 卡渲染：session/start 轻量探测（不建会话行的场景复用 bootstrap 后） */
function renderProbeCards() {
  fetch("/api/session/probe-cards", { headers: { "X-Anon-Id": Anon.get() } })
    .then((r) => (r.ok ? r.json() : null))
    .then((d) => { if (d) { renderVisit(d.visit_probe); renderFakeDoor(d.fakedoor_enabled); } })
    .catch(() => {});
}

function show(el) { el && el.classList.remove("hidden"); }
function hide(el) { el && el.classList.add("hidden"); }

/* ================= 主页：选餐流程 ================= */
const Quiz = { sid: null, lastQ: null, fromLocal: false, picked: false };

/* ---------- 回访卡（FR-16/18；被记得的闭环，服务端 ≤1 次/人/周频控） ---------- */
function renderVisit(vp) {
  if (!vp || !vp.enabled || !vp.dish_name) return;
  const box = $("visit-card");
  $("visit-q").textContent = `昨晚的『${vp.dish_name}』，还对味吗？`;
  box.classList.remove("hidden");
  track("visit_probe_show", { dish_slug: vp.dish_name });
  [...box.querySelectorAll(".visit-chip")].forEach((b) => b.onclick = async () => {
    try {
      await api("/api/visit-report", { method: "POST",
        body: JSON.stringify({ anon_id: Anon.get(), answer: b.dataset.v,
          dish_slug: vp.dish_name }) });
      box.classList.add("hidden");
      $("visit-done").textContent = b.dataset.v === "unsatisfied" ?
        "记住了，下次绕开它。" : "好嘞，这类给你记上。";
      $("visit-done").classList.remove("hidden");
      setTimeout(() => {                   /* P1-4：确认语可见 3s 后再撤卡 */
        const card = $("visit-card");
        if (card) card.classList.add("hidden");
      }, 3000);
      track("visit_answer", { v: b.dataset.v, dish_slug: vp.dish_name });
    } catch (e) {
      box.classList.add("hidden");                 // 429＝本周已答，静默收起
    }
  });
}

/* ---------- 诚实假门（FR-17，M3；config.fakedoor.enabled 翻转才渲染） ---------- */
function renderFakeDoor(enabled) {
  if (!enabled) return;
  const box = $("fakedoor-card");
  box.classList.remove("hidden");
  track("fakedoor_show", {});
  $("fd-register").onclick = async () => {
    try {
      await api("/api/fakedoor/register", { method: "POST",
        body: JSON.stringify({ anon_id: Anon.get() }) });
      $("fd-register").disabled = true;
      $("fd-register").textContent = "已登记";
      $("fd-done").classList.remove("hidden");
      track("fakedoor_register", {});
    } catch (e) { /* 静默：登记失败不影响主流程 */ }
  };
}

async function startQuiz() {
  hide($("screen-start")); hide($("screen-quiz"));
  const hint = $("taste-hint"); if (hint) hint.textContent = "";
  show($("screen-wait"));
  const { status, body } = await api("/api/quiz/session", { method: "POST" });
  if (status !== 200 || !body.session_id) { quizFail(); return; }
  Quiz.sid = body.session_id;
  await askNext();
}

async function askNext() {
  show($("screen-wait"));
  hide($("screen-quiz"));
  let { status, body } = await api(`/api/quiz/${Quiz.sid}/next`);
  if (status === 404) { await startQuiz(); return; }
  if (status !== 200) { quizFail(); return; }
  if (body.done) { await doFinalize(); return; }   // 引擎收口终裁：done 响应无 options（顺序 bug 修复 2026-09-15）
  if (!Array.isArray(body.options) || !body.options.length) { quizFail(); return; }
  hide($("screen-wait"));
  Quiz.lastQ = body;
  Quiz.picked = false;                     // P2：新题解锁点选锁
  renderQuestion(body);
  show($("screen-quiz"));
}

function renderQuestion(q) {
  $("step-num").textContent = (q.step + 1);
  $("quiz-q").textContent = q.question;
  const grid = $("quiz-cards");
  grid.innerHTML = "";
  const _n = q.options.length;
  grid.className = "flash-grid" + (_n > 3 ? " fan" : _n === 2 ? " two" : _n === 1 ? " one" : "");
  q.source === "local" && (Quiz.fromLocal = true);
  q.options.forEach((o, i) => {
    const b = document.createElement("button");
    b.className = "flash-card";
    b.style.setProperty("--i", i);
    b.textContent = o.text;
    b.setAttribute("aria-pressed", "false");
    b.setAttribute("role", "button");
    b.addEventListener("click", () => pickOption(o, b));
    grid.appendChild(b);
  });
}

async function pickOption(opt, btn) {
  // P2 修复：点选锁（双击双写防御——首点即锁全卡组）
  if (Quiz.picked) return;
  Quiz.picked = true;
  btn.setAttribute("aria-pressed", "true");
  $("quiz-cards").classList.add("out");
  await api(`/api/quiz/${Quiz.sid}/answer`, {
    method: "POST",
    body: JSON.stringify({
      option_id: opt.id, option_text: opt.text,
      question: Quiz.lastQ.question,
      from_local_bank: Quiz.lastQ.source === "local",
      all_options: Quiz.lastQ.options || [],
    }),
  });
  setTimeout(async () => {
    if (Quiz.lastQ.should_stop) { await doFinalize(); }
    else { await askNext(); }
  }, 260);
}

async function doFinalize() {
  hide($("screen-quiz"));
  show($("screen-wait"));
  const { status, body } = await api(`/api/quiz/${Quiz.sid}/finalize`, { method: "POST" });
  hide($("screen-wait"));
  if (status !== 200 || !body.name) { quizFail(); return; }
  showResult(body);
}

function showResult(r) {
  show($("screen-result"));
  Quiz.dish_slug = r.dish_slug || "";
  const acc = $("btn-accept"); if (acc) acc.disabled = false;
  renderSwapCounter(r.swaps_left);
  $("dish-name").textContent = r.name;          // aria-live=assertive → 屏幕阅读器播报
  $("dish-reason").textContent = r.reason || "";
  $("dish-tags").textContent = (r.tags || []).join(" · ");
}

/* ================= 各页入口 ================= */
document.addEventListener("DOMContentLoaded", async () => {
  initTheme();
  await bootstrapIdentity();
  renderProbeCards();

  // 隐私弹窗：仅首访展示一次
  if (!localStorage.getItem("wte_seen_privacy") && $("privacy-modal")) {
    show($("privacy-modal"));
  }
  if ($("btn-privacy-ok")) $("btn-privacy-ok").onclick = () => {
    localStorage.setItem("wte_seen_privacy", "1");
    hide($("privacy-modal"));
  };

  // --- 主页 ---
  if ($("btn-start")) $("btn-start").onclick = startQuiz;
  if ($("btn-quit")) $("btn-quit").onclick = () => location.reload();
  // 换一＝灯箱换片（P0-1 设计评审 2026-09-23）：不重答、留结果屏、剩 n 计数
  if ($("btn-again")) $("btn-again").onclick = async () => {
    const btn = $("btn-again");
    if (btn.disabled) return;
    btn.disabled = true; btn.textContent = "换片中…";
    const { status, body } = await api(`/api/quiz/${Quiz.sid}/swap`, { method: "POST" });
    if (status === 409) {                       // 耗尽：打烊态（服务端已留痕）
      btn.textContent = "今天的换一次数用完了";
      const h = $("swap-hint");
      if (h) h.textContent = "就吃这个吧，明天再来翻牌。";
      return;
    }
    if (status !== 200) {
      btn.disabled = false; btn.textContent = "换一个";
      const hint = $("taste-hint");
      if (hint) hint.textContent = "换片开小差了，再点一次试试";
      return;
    }
    show($("screen-wait"));
    hide($("screen-result"));
    const fin = await api(`/api/quiz/${Quiz.sid}/finalize`, { method: "POST" });
    hide($("screen-wait"));
    if (fin.status === 200 && fin.body.name) {
      showResult(fin.body);
      renderSwapCounter(fin.body.swaps_left);
    } else {
      quizFail(); return;
    }
  };
  // 确认推荐（2026-09-16 owner 拍板去除第三方外卖跳转）：accept 事件保留＝
  // 「用户确认了这道推荐」信号（味觉记忆＋北极星口径变更见迭代日志）；
  // /go 302 跳转链路停用（后端端点保留，前端无入口）。
  if ($("btn-accept")) $("btn-accept").onclick = async () => {
    const btn = $("btn-accept");
    btn.disabled = true;
    const { status } = await api(`/api/quiz/${Quiz.sid}/accept`, {
      method: "POST", body: JSON.stringify({ dish_slug: Quiz.dish_slug || "" }),
    });
    if (status === 200) {
      btn.textContent = "已记下 ✓（去「味觉记忆」打分，下次更准）";
      const hint = $("taste-hint");
      if (hint) hint.textContent = "去「味觉记忆」打分，下次推荐更准";
    } else {
      btn.disabled = false;
      const hint = $("taste-hint");
      if (hint) hint.textContent = "没记上，再点一次试试";
    }
  };

  // --- 身份页 ---
  if ($("anon-id-box")) initIdentityPage();

  // --- 记忆页 ---
  if ($("memory-list")) initMemoryPage();
});

/* ================= 身份页 ================= */
async function initIdentityPage() {
  const me = await bootstrapIdentity();
  $("anon-id-box").textContent = me.anon_id || Anon.get();
  if (me.has_passphrase) $("pass-heading").textContent = "更换口令";

  $("btn-copy").onclick = async () => {
    try {
      await navigator.clipboard.writeText($("anon-id-box").textContent);
      $("copy-hint").textContent = "已复制";
    } catch (e) { $("copy-hint").textContent = "复制失败，请手动长按选择"; }
  };

  $("btn-set-pass").onclick = async () => {
    const p = $("pass-input").value;
    const { body, status } = await api("/api/identity/passphrase",
      { method: "POST", body: JSON.stringify({ passphrase: p }) });
    $("pass-hint").textContent = status === 200 ? "口令已保存" : (body.error && body.error.message || "设置失败");
    if (status === 200) $("pass-input").value = "";
  };

  $("btn-recover").onclick = async () => {
    const { body, status } = await api("/api/identity/recover", {
      method: "POST",
      body: JSON.stringify({ anon_id: $("recover-id").value.trim(), passphrase: $("recover-pass").value }),
    });
    if (status === 200) {
      Anon.set(body.anon_id);
      $("recover-hint").textContent = "找回成功，已切换到该代号";
      setTimeout(() => location.reload(), 600);
    } else {
      $("recover-hint").textContent = (body.error && body.error.message) || "找回失败";
    }
  };

  $("btn-clear").onclick = async () => {
    if (!confirm("确定清空全部选餐记录与口味反馈？此操作不可恢复。")) return;
    await api("/api/identity/data", { method: "DELETE" });
    $("clear-hint").textContent = "已清空";
  };

  // 主题三键（P1-5：选中态 aria-pressed 回显）
  const set = (mode, btn) => {
    localStorage.setItem("wte_theme_mode", mode);
    document.body.dataset.theme = resolvedTheme(mode);
    ["theme-auto", "theme-day", "theme-night"].forEach((id) => {
      const b = $(id);
      if (b) b.setAttribute("aria-pressed", String(b === btn));
    });
  };
  set(localStorage.getItem("wte_theme_mode") || "auto", $("theme-auto"));
  $("theme-auto").onclick = () => set("auto", $("theme-auto"));
  $("theme-day").onclick = () => set("day", $("theme-day"));
  $("theme-night").onclick = () => set("night", $("theme-night"));
}

/* ================= 记忆页 ================= */
async function initMemoryPage() {
  const { body } = await api("/api/memory");
  const wrap = $("memory-list");
  const s = body.summary || {};
  $("memory-summary").textContent =
    `已记录 ${(body.items || []).length} 道菜 · ` +
    `对味 ${(s.liked || []).length} 类标签 / 不喜欢 ${(s.disliked || []).length} 类标签`;
  if (!(body.items || []).length) {
    wrap.innerHTML = '<p class="hint">还没有记录。先去选餐，得到一个推荐后再来反馈吧。</p>';
    return;
  }
  Memory.items = body.items;
  renderMemory();
  // 多维度筛选：名称模糊 / 场景 / 评价 / 时间，任一变化即重渲染
  ["f-kw", "f-scene", "f-fb", "f-time"].forEach((id) => {
    if ($(id)) $(id).addEventListener("input", renderMemory);
  });
}

const Memory = { items: [] };
const esc = (s) => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function memoryFiltered() {
  const kw = ($("f-kw") && $("f-kw").value || "").trim().toLowerCase();
  const scene = ($("f-scene") && $("f-scene").value) || "";
  const fb = ($("f-fb") && $("f-fb").value) || "";
  const days = Number(($("f-time") && $("f-time").value) || 0);
  const cutoff = days ? Date.now() - days * 86400_000 : 0;
  return Memory.items.filter((it) => {
    if (kw && !(it.name || "").toLowerCase().includes(kw)) return false;
    if (scene && it.meal_scenario !== scene) return false;
    if (fb === "unrated" && it.feedback != null) return false;
    if (["1", "0", "-1"].includes(fb) && String(it.feedback) !== fb) return false;
    if (cutoff && Date.parse(it.created_at || "") < cutoff) return false;
    return true;
  });
}

function renderMemory() {
  const wrap = $("memory-list");
  const items = memoryFiltered();
  const empty = $("memory-empty");
  if (empty) empty.classList.toggle("hidden", items.length > 0);
  wrap.innerHTML = "";
  for (const it of items) {
    const row = document.createElement("div");
    row.className = "memrow";
    // 完整答题路径：问题带编号，选项做方框（单选样式），高亮用户所选
    let pathHtml = "";
    (it.question_log || []).forEach((step, i) => {
      const opts = (step.options && step.options.length)
        ? step.options
        : [{ id: step.option_id, text: step.option_text }];
      const boxes = opts.map((o) => {
        const chosen = o.id === step.option_id || o.text === step.option_text;
        return `<li class="optbox ${chosen ? "picked" : ""}">`
          + `<span class="opt-dot" aria-hidden="true">${chosen ? "●" : "○"}</span>`
          + `<span class="opt-text">${esc(o.text)}</span></li>`;
      }).join("");
      pathHtml += `<div class="qstep"><p class="qstep-q">`
        + `<span class="qno num">${i + 1}</span> ${esc(step.question)}</p>`
        + `<ul class="qstep-opts">${boxes}</ul></div>`;
    });
    row.innerHTML = `
      <div class="memmeta">
        <strong>${esc(it.name)}</strong>
        <span class="hint num">${it.meal_scenario ? "·" + esc(it.meal_scenario) : ""} ${esc((it.created_at || "").slice(5, 10))}</span>
      </div>
      <p class="hint">${esc(it.reason || "")}</p>
      ${pathHtml ? `<details class="path"><summary>当时怎么选的（${(it.question_log || []).length} 步）</summary>${pathHtml}</details>` : ""}
      <div class="fbrow" role="group" aria-label="对${esc(it.name)}的反馈">
        <button data-id="${it.id}" data-score="1" class="fb ${it.feedback === 1 ? "on" : ""}">对味 +1</button>
        <button data-id="${it.id}" data-score="0" class="fb ${it.feedback === 0 ? "on" : ""}">一般 0</button>
        <button data-id="${it.id}" data-score="-1" class="fb ${it.feedback === -1 ? "on" : ""}">不推荐 -1</button>
      </div>`;
    wrap.appendChild(row);
  }
  wrap.querySelectorAll(".fb").forEach((b) => b.onclick = async () => {
    await api(`/api/memory/${b.dataset.id}/feedback`, {
      method: "POST", body: JSON.stringify({ score: Number(b.dataset.score) }),
    });
    // 只清当前这一行的高亮，勿动其它已反馈记录（历史 bug：整页 querySelectorAll 误清）
    b.closest(".fbrow").querySelectorAll(".fb").forEach((x) => x.classList.remove("on"));
    b.classList.add("on");
  });
}
