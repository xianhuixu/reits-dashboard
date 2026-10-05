/* ============================================================
 * page-agent-loader.js — 在 REITs Dashboard 内嵌 page-agent（阿里开源页内 GUI Agent）
 *
 * 设计原则：
 *  - 懒加载：page-agent 包（~230KB）只在用户首次点击 AI 按钮时才拉取，不影响首屏
 *  - 密钥安全：静态站点无法保密 API Key，因此提供两种模式——
 *      1) 演示模式：使用 page-agent 官方免费测试 LLM（有速率限制，仅用于体验）
 *      2) 自带密钥（BYOK）：用户填自己的 OpenAI 兼容端点（如阿里云百炼 DashScope），
 *         仅保存在访问者浏览器 localStorage，不上传任何服务器
 *  - CDN 双保险：jsDelivr 主源 + npmmirror 国内镜像自动回退
 *  - 加载策略：优先 fetch+注入（绕过个别环境对跨域 script 标签的阻塞），失败退化为 script 标签
 * ============================================================ */
(function () {
  'use strict';

  var VERSION = '1.12.4';
  var CDN_PRIMARY = 'https://cdn.jsdelivr.net/npm/page-agent@' + VERSION + '/dist/iife/page-agent.demo.js?autoInit=false';
  var CDN_MIRROR = 'https://registry.npmmirror.com/page-agent/' + VERSION + '/files/dist/iife/page-agent.demo.js?autoInit=false';
  var SCRIPT_TIMEOUT = 12000;

  var LS_KEY = 'rd-ai-config';

  /* 演示模式：page-agent 官方免费测试 LLM（见 alibaba/page-agent README，仅限技术评估） */
  var DEMO_CFG = {
    mode: 'demo',
    model: 'qwen3.5-plus',
    baseURL: 'https://page-ag-testing-ohftxirgbn.cn-shanghai.fcapp.run',
    apiKey: 'NA'
  };

  var BYOK_DEFAULTS = {
    baseURL: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    model: 'qwen3.5-plus'
  };

  /* ---------- 工具 ---------- */

  function $(id) { return document.getElementById(id); }

  function loadCfg() {
    try {
      var raw = localStorage.getItem(LS_KEY);
      if (!raw) return null;
      var cfg = JSON.parse(raw);
      if (!cfg || !cfg.baseURL || !cfg.model) return null;
      if (cfg.apiKey === undefined || cfg.apiKey === null) cfg.apiKey = '';
      return cfg;
    } catch (e) { return null; }
  }

  function saveCfg(cfg) {
    try { localStorage.setItem(LS_KEY, JSON.stringify(cfg)); } catch (e) { /* 隐私模式下忽略 */ }
  }

  function clearCfg() {
    try { localStorage.removeItem(LS_KEY); } catch (e) { /* ignore */ }
  }

  /* 依次尝试多个 CDN；单个 URL 内部先 fetch+注入，失败退化为 script 标签（带超时） */
  function loadEngine(urls) {
    return new Promise(function (resolve, reject) {
      var i = 0;
      function tryNext() {
        if (i >= urls.length) { reject(new Error('all-cdn-failed')); return; }
        var url = urls[i++];
        fetch(url)
          .then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.text();
          })
          .then(function (code) {
            var s = document.createElement('script');
            s.textContent = code;
            document.head.appendChild(s);
            if (typeof window.PageAgent === 'function') { resolve(); return; }
            s.remove();
            tryNext();
          })
          .catch(function () { viaScriptTag(url); });
      }
      function viaScriptTag(url) {
        var s = document.createElement('script');
        s.src = url;
        s.async = true;
        s.crossOrigin = 'anonymous';
        var done = false;
        function once(ok) {
          if (done) return;
          done = true;
          clearTimeout(timer);
          if (ok && typeof window.PageAgent === 'function') { resolve(); }
          else { s.remove(); tryNext(); }
        }
        var timer = setTimeout(function () { once(false); }, SCRIPT_TIMEOUT);
        s.onload = function () { once(true); };
        s.onerror = function () { once(false); };
        document.head.appendChild(s);
      }
      tryNext();
    });
  }

  /* ---------- 启动按钮 + 设置齿轮 ---------- */

  function buildLauncher() {
    var wrap = document.createElement('div');
    wrap.id = 'rdAiWrap';
    var btn = document.createElement('button');
    btn.id = 'rdAiLauncher';
    btn.type = 'button';
    btn.setAttribute('aria-label', '打开 AI 助手');
    btn.textContent = 'AI';
    var gear = document.createElement('button');
    gear.id = 'rdAiGear';
    gear.type = 'button';
    gear.setAttribute('aria-label', '重新配置 AI 助手');
    gear.textContent = '⚙';
    gear.hidden = true;
    wrap.appendChild(gear);
    wrap.appendChild(btn);
    document.body.appendChild(wrap);
    return { btn: btn, gear: gear };
  }

  /* ---------- 设置卡片 ---------- */

  function buildCard() {
    var wrap = document.createElement('div');
    wrap.id = 'rdAiCard';
    wrap.setAttribute('role', 'dialog');
    wrap.setAttribute('aria-label', 'AI 助手设置');
    wrap.hidden = true;
    wrap.innerHTML =
      '<div class="rd-ai-card-head">' +
        '<strong>AI 助手</strong>' +
        '<button type="button" class="rd-ai-x" id="rdAiClose" aria-label="关闭">×</button>' +
      '</div>' +
      '<p class="rd-ai-desc">基于 <a href="https://github.com/alibaba/page-agent" target="_blank" rel="noopener">page-agent</a> 的页内智能体，可用自然语言操作本看板：<br>' +
      '<span class="rd-ai-eg">例：「切换到研究页」「打开中金厦门安居的详情」「帮我看看涨幅前 5 的 REITs」</span></p>' +
      '<div class="rd-ai-sec">' +
        '<button type="button" id="rdAiDemo" class="rd-ai-btn rd-ai-btn-primary">一键体验（演示模型，无需密钥）</button>' +
        '<p class="rd-ai-note">使用 page-agent 官方免费测试模型，有速率限制，仅用于体验评估。</p>' +
      '</div>' +
      '<div class="rd-ai-divider"><span>或自带模型密钥（BYOK）</span></div>' +
      '<div class="rd-ai-form">' +
        '<label>API Base URL<input id="rdAiBase" placeholder="' + BYOK_DEFAULTS.baseURL + '" autocomplete="off"></label>' +
        '<label>API Key<input id="rdAiKey" type="password" placeholder="sk-..." autocomplete="off"></label>' +
        '<label>模型名<input id="rdAiModel" placeholder="' + BYOK_DEFAULTS.model + '" autocomplete="off"></label>' +
        '<button type="button" id="rdAiSave" class="rd-ai-btn rd-ai-btn-primary">保存并开始</button>' +
        '<p class="rd-ai-note">密钥仅存储在你自己的浏览器 localStorage，支持任何 OpenAI 兼容端点（DashScope / OpenAI / OpenRouter / Ollama 等）。</p>' +
      '</div>' +
      '<div class="rd-ai-foot">' +
        '<button type="button" id="rdAiReset" class="rd-ai-link" hidden>清除已保存配置</button>' +
      '</div>';
    document.body.appendChild(wrap);

    $('rdAiClose').addEventListener('click', hideCard);
    $('rdAiDemo').addEventListener('click', function () {
      saveCfg(DEMO_CFG);
      syncGear();
      bootAgent(DEMO_CFG);
    });
    $('rdAiSave').addEventListener('click', function () {
      var baseURL = $('rdAiBase').value.trim() || BYOK_DEFAULTS.baseURL;
      var apiKey = $('rdAiKey').value.trim();
      var model = $('rdAiModel').value.trim() || BYOK_DEFAULTS.model;
      if (!apiKey) { toast('请填写 API Key（或改用上方演示模式）'); return; }
      var cfg = { mode: 'custom', baseURL: baseURL, apiKey: apiKey, model: model };
      saveCfg(cfg);
      syncGear();
      bootAgent(cfg);
    });
    $('rdAiReset').addEventListener('click', function () {
      clearCfg();
      if (window.__rdAgent && window.__rdAgent.dispose) { try { window.__rdAgent.dispose(); } catch (e) {} }
      window.__rdAgent = null;
      updateResetVisibility();
      syncGear();
      toast('已清除配置');
    });
    return wrap;
  }

  function prefillForm() {
    var cfg = loadCfg();
    if (!cfg || cfg.mode !== 'custom') return;
    if (cfg.baseURL) $('rdAiBase').value = cfg.baseURL;
    if (cfg.model) $('rdAiModel').value = cfg.model;
    if (cfg.apiKey) $('rdAiKey').value = cfg.apiKey;
  }

  function showCard() {
    prefillForm();
    updateResetVisibility();
    $('rdAiCard').hidden = false;
  }
  function hideCard() { $('rdAiCard').hidden = true; }
  function updateResetVisibility() {
    var has = !!loadCfg();
    var r = $('rdAiReset');
    if (r) r.hidden = !has;
  }

  /* ---------- Toast ---------- */

  var toastTimer = null;
  function toast(msg) {
    var t = $('rdAiToast');
    if (!t) {
      t = document.createElement('div');
      t.id = 'rdAiToast';
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.classList.remove('show'); }, 3200);
  }

  /* ---------- Agent 启动 ---------- */

  var bootPromise = null;

  function bootAgent(cfg) {
    if (!bootPromise) {
      bootPromise = loadEngine([CDN_PRIMARY, CDN_MIRROR]);
    }
    toast('正在加载 AI 引擎…');
    bootPromise.then(function () {
      try {
        if (!window.__rdAgent) {
          window.__rdAgent = new window.PageAgent({
            model: cfg.model,
            baseURL: cfg.baseURL,
            apiKey: cfg.apiKey,
            language: 'zh-CN'
          });
        }
        hideCard();
        if (window.__rdAgent.panel && window.__rdAgent.panel.show) window.__rdAgent.panel.show();
      } catch (e) {
        console.error('[rd-ai] init failed:', e);
        toast('初始化失败：' + (e && e.message ? e.message : e));
      }
    }).catch(function () {
      bootPromise = null;
      toast('AI 引擎加载失败：CDN 不可达，请检查网络后重试');
    });
  }

  /* ---------- 样式（跟随站点 CSS 变量，自适应亮/暗/护眼主题） ---------- */

  function injectStyles() {
    var css =
      '#rdAiWrap{position:fixed;right:22px;bottom:22px;z-index:2147483639}' +
      '#rdAiLauncher{width:48px;height:48px;border-radius:50%;border:none;cursor:pointer;' +
        'font:700 15px/1 system-ui,sans-serif;color:#fff;' +
        'background:var(--accent,#2563eb);box-shadow:0 4px 16px rgba(0,0,0,.28);' +
        'transition:transform .15s ease,box-shadow .15s ease}' +
      '#rdAiLauncher:hover{transform:scale(1.08);box-shadow:0 6px 22px rgba(0,0,0,.34)}' +
      '#rdAiLauncher:active{transform:scale(.96)}' +
      '#rdAiGear{position:absolute;top:-6px;left:-6px;width:22px;height:22px;border-radius:50%;' +
        'border:1px solid var(--line,#d0d7de);background:var(--panel,#fff);color:var(--tx3,#6e7781);' +
        'font-size:11px;line-height:1;cursor:pointer;padding:0;box-shadow:0 2px 6px rgba(0,0,0,.18)}' +
      '#rdAiGear:hover{color:var(--accent,#2563eb)}' +
      '#rdAiCard{position:fixed;right:22px;bottom:82px;z-index:2147483639;width:330px;max-width:calc(100vw - 32px);' +
        'background:var(--panel,#fff);color:var(--tx,#0d1117);border:1px solid var(--line,#d0d7de);' +
        'border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,.25);padding:16px 16px 12px;' +
        'font:13px/1.6 system-ui,sans-serif}' +
      '#rdAiCard .rd-ai-card-head{display:flex;justify-content:space-between;align-items:center;font-size:14px}' +
      '#rdAiCard .rd-ai-x{border:none;background:transparent;color:var(--tx3,#6e7781);font-size:18px;cursor:pointer;line-height:1;padding:2px 6px}' +
      '#rdAiCard .rd-ai-x:hover{color:var(--tx,#0d1117)}' +
      '#rdAiCard .rd-ai-desc{margin:8px 0 10px;color:var(--tx2,#3d444d);font-size:12.5px}' +
      '#rdAiCard .rd-ai-desc a{color:var(--accent,#2563eb)}' +
      '#rdAiCard .rd-ai-eg{color:var(--tx3,#6e7781)}' +
      '#rdAiCard .rd-ai-sec{margin-bottom:4px}' +
      '#rdAiCard .rd-ai-btn{width:100%;padding:9px 12px;border-radius:10px;border:none;cursor:pointer;font-weight:600;font-size:13px}' +
      '#rdAiCard .rd-ai-btn-primary{background:var(--accent,#2563eb);color:#fff}' +
      '#rdAiCard .rd-ai-btn-primary:hover{filter:brightness(1.08)}' +
      '#rdAiCard .rd-ai-note{font-size:11.5px;color:var(--tx3,#6e7781);margin:6px 0 0}' +
      '#rdAiCard .rd-ai-divider{display:flex;align-items:center;gap:8px;margin:12px 0;color:var(--tx3,#6e7781);font-size:11.5px}' +
      '#rdAiCard .rd-ai-divider::before,#rdAiCard .rd-ai-divider::after{content:"";flex:1;height:1px;background:var(--line,#d0d7de)}' +
      '#rdAiCard .rd-ai-form label{display:block;margin-bottom:8px;font-size:12px;color:var(--tx2,#3d444d)}' +
      '#rdAiCard .rd-ai-form input{width:100%;box-sizing:border-box;margin-top:3px;padding:7px 10px;font:inherit;font-size:12.5px;' +
        'background:var(--panel2,#f5f7fa);border:1px solid var(--line,#d0d7de);border-radius:8px;color:var(--tx,#0d1117)}' +
      '#rdAiCard .rd-ai-foot{margin-top:10px;text-align:right}' +
      '#rdAiCard .rd-ai-link{border:none;background:none;color:var(--tx3,#6e7781);font-size:12px;cursor:pointer;text-decoration:underline}' +
      '#rdAiToast{position:fixed;right:22px;bottom:82px;z-index:2147483646;max-width:calc(100vw - 32px);' +
        'background:#1f2937;color:#fff;padding:9px 14px;border-radius:10px;font:12.5px/1.5 system-ui,sans-serif;' +
        'box-shadow:0 8px 24px rgba(0,0,0,.3);opacity:0;pointer-events:none;transform:translateY(6px);' +
        'transition:opacity .2s ease,transform .2s ease}' +
      '#rdAiToast.show{opacity:1;transform:translateY(0)}';
    var style = document.createElement('style');
    style.id = 'rdAiStyles';
    style.textContent = css;
    document.head.appendChild(style);
  }

  /* ---------- 启动 ---------- */

  var gearBtn = null;
  function syncGear() { if (gearBtn) gearBtn.hidden = !loadCfg(); }

  function init() {
    injectStyles();
    var ui = buildLauncher();
    gearBtn = ui.gear;
    buildCard();
    syncGear();
    ui.btn.addEventListener('click', function () {
      var cfg = loadCfg();
      if (cfg) bootAgent(cfg);
      else {
        var card = $('rdAiCard');
        if (card.hidden) showCard(); else hideCard();
      }
    });
    ui.gear.addEventListener('click', function (e) {
      e.stopPropagation();
      var card = $('rdAiCard');
      if (card.hidden) showCard(); else hideCard();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
