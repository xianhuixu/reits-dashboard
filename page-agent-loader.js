/* ============================================================
 * page-agent-loader.js — 在 REITs Dashboard 内嵌 page-agent（阿里开源页内 GUI Agent）
 *
 * 设计原则：
 *  - 懒加载：page-agent 包（~230KB）只在用户首次点击 AI 按钮时才拉取，不影响首屏
 *  - 一键体验：主按钮直接进入官方演示模型，不弹密钥表单；齿轮才打开 BYOK
 *  - 密钥安全：BYOK 仅存访问者 localStorage，不上传任何服务器
 *  - CDN 双保险：jsDelivr 主源 + npmmirror 国内镜像自动回退
 *  - 加载策略：优先 script 标签（保留 ?autoInit=false）；失败再 fetch+注入并禁用 demo 自启
 * ============================================================ */
(function () {
  'use strict';

  var VERSION = '1.12.4';
  /* demo IIFE is the only browser bundle; ?autoInit=false prevents its built-in agent */
  var CDN_PRIMARY = 'https://cdn.jsdelivr.net/npm/page-agent@' + VERSION + '/dist/iife/page-agent.demo.js?autoInit=false';
  var CDN_MIRROR = 'https://registry.npmmirror.com/page-agent/' + VERSION + '/files/dist/iife/page-agent.demo.js?autoInit=false';
  var SCRIPT_TIMEOUT = 12000;

  var LS_KEY = 'rd-ai-config';

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

  /* 帮助 agent 理解本站导航（hash/按钮切换，非多页跳转） */
  var PAGE_INSTRUCTIONS =
    '你在「公募 REITs 投研看板」页内。用点击完成操作，不要修改地址栏。\n' +
    '主导航（侧栏或顶部）：市场总览、研究分析、配置与风险、机构间市场。\n' +
    '「研究页」= 点击「研究分析」；「配置」=「配置与风险」；「机构」=「机构间市场」。\n' +
    '市场总览下有子页：行情总览 / 新闻与公告 / 发改委推荐 / 上交所申报 / 深交所申报 等，点对应子导航。\n' +
    '主题切换在右上角（浅色 / 护眼 / 深色）。个券详情可通过搜索或热力图格子进入。\n' +
    '回答尽量简洁，用中文。';

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
    try { localStorage.setItem(LS_KEY, JSON.stringify(cfg)); } catch (e) { /* 隐私模式忽略 */ }
  }

  function clearCfg() {
    try { localStorage.removeItem(LS_KEY); } catch (e) { /* ignore */ }
  }

  function cfgKey(cfg) {
    return [cfg.mode || '', cfg.baseURL || '', cfg.model || '', cfg.apiKey || ''].join('\x1f');
  }

  /* 禁用 demo IIFE 在 fetch 注入时的自动初始化（无 currentScript 时会默认 autoInit=true） */
  function disableDemoAutoInit(code) {
    return String(code)
      .replace(
        /autoInit=currentScriptURL\?\.searchParams\.get\(`autoInit`\)!==`false`/g,
        'autoInit=false'
      )
      .replace(
        /autoInit=currentScriptURL\?\.searchParams\.get\("autoInit"\)!=="false"/g,
        'autoInit=false'
      );
  }

  function disposeAutoAgent() {
    if (window.pageAgent && typeof window.pageAgent.dispose === 'function') {
      try { window.pageAgent.dispose(); } catch (e) { /* ignore */ }
    }
    window.pageAgent = null;
  }

  function loadEngine(urls) {
    return new Promise(function (resolve, reject) {
      var i = 0;
      function tryNext() {
        if (i >= urls.length) { reject(new Error('all-cdn-failed')); return; }
        var url = urls[i++];
        /* 1) script 标签：URL 上的 ?autoInit=false 生效 */
        viaScriptTag(url).then(resolve).catch(function () {
          /* 2) fetch+注入：改写源码禁用 autoInit，并清掉误建的 agent */
          fetch(url)
            .then(function (r) {
              if (!r.ok) throw new Error('HTTP ' + r.status);
              return r.text();
            })
            .then(function (code) {
              var s = document.createElement('script');
              s.textContent = disableDemoAutoInit(code);
              document.head.appendChild(s);
              return new Promise(function (res) {
                setTimeout(function () {
                  disposeAutoAgent();
                  if (typeof window.PageAgent === 'function') resolve();
                  else { try { s.remove(); } catch (e) {} tryNext(); }
                  res();
                }, 0);
              });
            })
            .catch(function () { tryNext(); });
        });
      }
      function viaScriptTag(url) {
        return new Promise(function (res, rej) {
          if (typeof window.PageAgent === 'function') { res(); return; }
          var s = document.createElement('script');
          s.src = url;
          s.async = true;
          s.crossOrigin = 'anonymous';
          var done = false;
          function once(ok) {
            if (done) return;
            done = true;
            clearTimeout(timer);
            if (ok && typeof window.PageAgent === 'function') {
              disposeAutoAgent();
              res();
            } else {
              try { s.remove(); } catch (e) {}
              rej(new Error('script-tag-failed'));
            }
          }
          var timer = setTimeout(function () { once(false); }, SCRIPT_TIMEOUT);
          s.onload = function () { once(true); };
          s.onerror = function () { once(false); };
          document.head.appendChild(s);
        });
      }
      tryNext();
    });
  }

  function buildLauncher() {
    var wrap = document.createElement('div');
    wrap.id = 'rdAiWrap';
    var btn = document.createElement('button');
    btn.id = 'rdAiLauncher';
    btn.type = 'button';
    btn.setAttribute('aria-label', '打开 AI 助手（演示模式）');
    btn.title = 'AI 助手';
    btn.textContent = 'AI';
    var gear = document.createElement('button');
    gear.id = 'rdAiGear';
    gear.type = 'button';
    gear.setAttribute('aria-label', 'AI 助手设置');
    gear.title = '设置（自带密钥 / 清除）';
    gear.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true" focusable="false"><path fill="currentColor" d="M19.14 12.94c.04-.31.06-.63.06-.94s-.02-.63-.06-.94l2.03-1.58a.5.5 0 0 0 .12-.64l-1.92-3.32a.5.5 0 0 0-.6-.22l-2.39.96a7.07 7.07 0 0 0-1.63-.94l-.36-2.54A.5.5 0 0 0 13.9 2h-3.8a.5.5 0 0 0-.49.42l-.36 2.54c-.58.23-1.12.54-1.63.94l-2.39-.96a.5.5 0 0 0-.6.22L2.81 8.48a.5.5 0 0 0 .12.64l2.03 1.58c-.04.31-.06.63-.06.94s.02.63.06.94L2.93 14.1a.5.5 0 0 0-.12.64l1.92 3.32c.14.24.43.34.68.24l2.39-.96c.5.4 1.05.71 1.63.94l.36 2.54c.05.24.25.42.49.42h3.8c.24 0 .44-.18.49-.42l.36-2.54c.58-.23 1.12-.54 1.63-.94l2.39.96c.25.1.54 0 .68-.24l1.92-3.32a.5.5 0 0 0-.12-.64l-2.03-1.58zM12 15.5A3.5 3.5 0 1 1 12 8.5a3.5 3.5 0 0 1 0 7z"/></svg>';
    wrap.appendChild(gear);
    wrap.appendChild(btn);
    document.body.appendChild(wrap);
    return { btn: btn, gear: gear };
  }

  function buildCard() {
    var wrap = document.createElement('div');
    wrap.id = 'rdAiCard';
    wrap.setAttribute('role', 'dialog');
    wrap.setAttribute('aria-label', 'AI 助手设置');
    wrap.hidden = true;
    wrap.innerHTML =
      '<div class="rd-ai-card-head">' +
        '<strong>AI 助手设置</strong>' +
        '<button type="button" class="rd-ai-x" id="rdAiClose" aria-label="关闭">×</button>' +
      '</div>' +
      '<p class="rd-ai-desc">主按钮可直接一键体验官方演示模型。此处仅在需要时配置自己的密钥（BYOK）。基于 <a href="https://github.com/alibaba/page-agent" target="_blank" rel="noopener">page-agent</a>。<br>' +
      '<span class="rd-ai-eg">例：「切换到研究页」「打开中金厦门安居的详情」「帮我看看涨幅前 5 的 REITs」</span></p>' +
      '<div class="rd-ai-sec">' +
        '<button type="button" id="rdAiDemo" class="rd-ai-btn rd-ai-btn-primary">重新进入演示模式</button>' +
        '<p class="rd-ai-note">官方免费测试模型，有速率限制，仅用于体验评估。</p>' +
      '</div>' +
      '<div class="rd-ai-divider"><span>或自带模型密钥（BYOK）</span></div>' +
      '<div class="rd-ai-form">' +
        '<label>API Base URL<input id="rdAiBase" placeholder="' + BYOK_DEFAULTS.baseURL + '" autocomplete="off"></label>' +
        '<label>API Key<input id="rdAiKey" type="password" placeholder="sk-..." autocomplete="off"></label>' +
        '<label>模型名<input id="rdAiModel" placeholder="' + BYOK_DEFAULTS.model + '" autocomplete="off"></label>' +
        '<button type="button" id="rdAiSave" class="rd-ai-btn rd-ai-btn-primary">保存并开始</button>' +
        '<p class="rd-ai-note">密钥仅存你自己的浏览器 localStorage，支持 DashScope / OpenAI / OpenRouter / Ollama 等兼容端点。</p>' +
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
      if (!apiKey) { toast('请填写 API Key（或改用演示模式）'); return; }
      var cfg = { mode: 'custom', baseURL: baseURL, apiKey: apiKey, model: model };
      saveCfg(cfg);
      syncGear();
      bootAgent(cfg);
    });
    $('rdAiReset').addEventListener('click', function () {
      clearCfg();
      disposeOurAgent();
      updateResetVisibility();
      syncGear();
      toast('已清除配置，主按钮将重新进入演示模式');
    });
    return wrap;
  }

  function prefillForm() {
    var cfg = loadCfg();
    if (!cfg || cfg.mode !== 'custom') {
      $('rdAiBase').value = '';
      $('rdAiKey').value = '';
      $('rdAiModel').value = '';
      return;
    }
    if (cfg.baseURL) $('rdAiBase').value = cfg.baseURL;
    if (cfg.model) $('rdAiModel').value = cfg.model;
    if (cfg.apiKey) $('rdAiKey').value = cfg.apiKey;
  }

  function showCard() {
    prefillForm();
    updateResetVisibility();
    $('rdAiCard').hidden = false;
  }
  function hideCard() { var c = $('rdAiCard'); if (c) c.hidden = true; }
  function updateResetVisibility() {
    var has = !!loadCfg();
    var r = $('rdAiReset');
    if (r) r.hidden = !has;
  }

  var toastTimer = null;
  function toast(msg, sticky) {
    var t = $('rdAiToast');
    if (!t) {
      t = document.createElement('div');
      t.id = 'rdAiToast';
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(toastTimer);
    if (!sticky) {
      toastTimer = setTimeout(function () { t.classList.remove('show'); }, 3200);
    }
  }
  function hideToast() {
    clearTimeout(toastTimer);
    var t = $('rdAiToast');
    if (t) t.classList.remove('show');
  }

  function disposeOurAgent() {
    if (window.__rdAgent && typeof window.__rdAgent.dispose === 'function' && !window.__rdAgent.disposed) {
      try { window.__rdAgent.dispose(); } catch (e) { /* ignore */ }
    }
    window.__rdAgent = null;
  }

  var bootPromise = null;

  function createAgent(cfg) {
    return new window.PageAgent({
      model: cfg.model,
      baseURL: cfg.baseURL,
      apiKey: cfg.apiKey,
      language: 'zh-CN',
      instructions: { system: PAGE_INSTRUCTIONS }
    });
  }

  function ensureAgent(cfg) {
    var key = cfgKey(cfg);
    var cur = window.__rdAgent;
    if (cur && !cur.disposed && cur.__rdKey === key) return cur;
    disposeOurAgent();
    disposeAutoAgent();
    var agent = createAgent(cfg);
    agent.__rdKey = key;
    window.__rdAgent = agent;
    return agent;
  }

  function bootAgent(cfg) {
    if (!bootPromise) {
      bootPromise = loadEngine([CDN_PRIMARY, CDN_MIRROR]);
    }
    toast('正在加载 AI 引擎…', true);
    bootPromise.then(function () {
      try {
        var agent = ensureAgent(cfg);
        hideCard();
        hideToast();
        if (agent.panel && typeof agent.panel.show === 'function') agent.panel.show();
      } catch (e) {
        console.error('[rd-ai] init failed:', e);
        hideToast();
        toast('初始化失败：' + (e && e.message ? e.message : e));
        showCard();
      }
    }).catch(function () {
      bootPromise = null;
      hideToast();
      toast('AI 引擎加载失败，可重试或改用自带密钥');
      showCard();
    });
  }

  function injectStyles() {
    var css =
      /* 桌面：右上横排（设置在左、AI 在右），避免小圆点叠在 AI 角上像未读角标；移动：右下 */
      '#rdAiWrap{position:fixed;z-index:2147483639;display:flex;flex-direction:row;align-items:center;gap:8px;' +
        'right:max(12px, env(safe-area-inset-right, 0px));' +
        'top:72px}' +
      '@media (max-width:640px){#rdAiWrap{top:auto;bottom:max(16px, env(safe-area-inset-bottom, 0px));right:max(12px, env(safe-area-inset-right, 0px));flex-direction:row;gap:8px}}' +
      '#rdAiLauncher{width:44px;height:44px;border-radius:50%;border:none;cursor:pointer;' +
        'font:700 14px/1 system-ui,sans-serif;color:#fff;' +
        'background:var(--accent,#2563eb);box-shadow:0 4px 16px rgba(0,0,0,.28);' +
        'transition:transform .15s ease,box-shadow .15s ease;' +
        'position:relative}' +
      /* 保险：清掉任何伪元素角标 / 未读计数 */
      '#rdAiLauncher::before,#rdAiLauncher::after,#rdAiWrap::before,#rdAiWrap::after{content:none!important;display:none!important}' +
      '@media (max-width:640px){#rdAiLauncher{width:40px;height:40px;font-size:13px}}' +
      '#rdAiLauncher:hover{transform:scale(1.08);box-shadow:0 6px 22px rgba(0,0,0,.34)}' +
      '#rdAiLauncher:active{transform:scale(.96)}' +
      /* 设置钮：独立控件，不用叠角小圆（易被看成未读 0） */
      '#rdAiGear{position:static;width:32px;height:32px;border-radius:10px;' +
        'border:1px solid var(--line,#d0d7de);background:var(--panel,#fff);color:var(--tx3,#6e7781);' +
        'display:inline-flex;align-items:center;justify-content:center;' +
        'font-size:0;line-height:0;cursor:pointer;padding:0;box-shadow:0 2px 8px rgba(0,0,0,.12)}' +
      '#rdAiGear svg{display:block}' +
      '#rdAiGear:hover{color:var(--accent,#2563eb);border-color:var(--accent,#2563eb)}' +
      '#rdAiGear.rd-ai-gear-on{color:var(--accent,#2563eb);border-color:var(--accent,#2563eb);background:var(--panel2,#f5f7fa)}' +
      /* 设置卡：桌面在按钮下方；移动靠顶部，避开「退回中性确认」与底栏 */
      '#rdAiCard{position:fixed;z-index:2147483639;width:330px;max-width:calc(100vw - 24px);' +
        'right:max(12px, env(safe-area-inset-right, 0px));top:124px;' +
        'max-height:calc(100vh - 140px);overflow:auto;' +
        'background:var(--panel,#fff);color:var(--tx,#0d1117);border:1px solid var(--line,#d0d7de);' +
        'border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,.25);padding:16px 16px 12px;' +
        'font:13px/1.6 system-ui,sans-serif}' +
      '@media (max-width:640px){#rdAiCard{top:64px;bottom:auto;max-height:calc(100vh - 96px);right:12px;left:12px;width:auto;max-width:none}}' +
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
      '#rdAiToast{position:fixed;z-index:2147483646;max-width:calc(100vw - 32px);' +
        'right:max(12px, env(safe-area-inset-right, 0px));top:124px;' +
        'background:var(--tx,#1f2937);color:var(--panel,#fff);padding:9px 14px;border-radius:10px;' +
        'font:12.5px/1.5 system-ui,sans-serif;border:1px solid var(--line2,transparent);' +
        'box-shadow:0 8px 24px rgba(0,0,0,.3);opacity:0;pointer-events:none;transform:translateY(6px);' +
        'transition:opacity .2s ease,transform .2s ease}' +
      '@media (max-width:640px){#rdAiToast{top:auto;bottom:64px}}' +
      '#rdAiToast.show{opacity:1;transform:translateY(0)}' +
      /* page-agent 面板：桌面略抬高；移动端限制展开高度，避免盖住时钟卡「退回中性确认」 */
      '#page-agent-runtime_agent-panel{bottom:max(24px, env(safe-area-inset-bottom, 0px)) !important}' +
      '@media (max-width:640px){' +
        /* 面板贴底但留出 AI 按钮；展开历史严格封顶，避免盖住时钟卡「退回中性确认」 */
        '#page-agent-runtime_agent-panel{bottom:max(76px, calc(24px + env(safe-area-inset-bottom, 0px))) !important}' +
        '#page-agent-runtime_agent-panel [class*="_historySection_"]{max-height:min(16vh, 130px) !important}' +
        '#page-agent-runtime_agent-panel [class*="_historySectionWrapper_"]{max-height:min(16vh, 130px) !important}' +
      '}' +
      '[data-theme="dark"] #page-agent-runtime_agent-panel,[data-theme="eye"] #page-agent-runtime_agent-panel{' +
        '--color-1:var(--accent,#58a6ff);--color-2:var(--gro,#bc8cff)}';
    var style = document.createElement('style');
    style.id = 'rdAiStyles';
    style.textContent = css;
    document.head.appendChild(style);
  }

  var gearBtn = null;
  function syncGear() { /* 齿轮始终可见，方便打开 BYOK；有配置时更醒目 */
    if (!gearBtn) return;
    gearBtn.hidden = false;
    gearBtn.classList.toggle('rd-ai-gear-on', !!loadCfg());
  }

  function init() {
    injectStyles();
    var ui = buildLauncher();
    gearBtn = ui.gear;
    buildCard();
    syncGear();

    /* 主按钮：一键演示（已保存 BYOK 则用 BYOK）；永不因缺密钥弹表单 */
    ui.btn.addEventListener('click', function () {
      var cfg = loadCfg();
      if (cfg && cfg.mode === 'custom' && cfg.apiKey) {
        bootAgent(cfg);
      } else {
        saveCfg(DEMO_CFG);
        syncGear();
        bootAgent(DEMO_CFG);
      }
    });
    /* 齿轮：才打开设置卡 */
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
