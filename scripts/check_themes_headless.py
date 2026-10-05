import json, time, subprocess, urllib.request, threading, sys
from websocket import create_connection

PORT = 9334
chrome = subprocess.Popen([
  "google-chrome","--headless=new","--disable-gpu","--no-sandbox",
  f"--remote-debugging-port={PORT}","--remote-allow-origins=*",
  "--user-data-dir=/tmp/chrome-rd-oper4","about:blank"
], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

def wait():
  for _ in range(80):
    try:
      urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1)
      return
    except Exception:
      time.sleep(0.1)
  err = chrome.stderr.read().decode()[:800]
  raise SystemExit("chrome not up: " + err)

wait()
print("chrome up", flush=True)

def new_page():
  req = urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?about:blank", method="PUT")
  with urllib.request.urlopen(req, timeout=5) as r:
    return json.loads(r.read().decode())

class CDP:
  def __init__(self, wsurl):
    self.ws = create_connection(wsurl, timeout=10)
    self.id = 0
    self.pending = {}
    self.console_errors = []
    self.page_errors = []
    self._stop = False
    self.t = threading.Thread(target=self._reader, daemon=True)
    self.t.start()
  def _reader(self):
    while not self._stop:
      try:
        msg = json.loads(self.ws.recv())
      except Exception:
        return
      if msg.get("id") in self.pending:
        self.pending[msg["id"]] = msg
      elif msg.get("method") == "Runtime.consoleAPICalled":
        if msg["params"].get("type") in ("error", "assert"):
          args = msg["params"].get("args") or []
          text = " ".join(str(a.get("value") or a.get("description") or a) for a in args)
          self.console_errors.append(text)
      elif msg.get("method") == "Runtime.exceptionThrown":
        ed = msg["params"].get("exceptionDetails") or {}
        self.page_errors.append(ed.get("text") or (ed.get("exception") or {}).get("description") or "exception")
  def send(self, method, params=None):
    self.id += 1
    mid = self.id
    self.pending[mid] = None
    self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    for _ in range(200):
      if self.pending[mid] is not None:
        msg = self.pending.pop(mid)
        if "error" in msg:
          raise RuntimeError(msg["error"])
        return msg.get("result")
      time.sleep(0.05)
    raise TimeoutError(method)
  def close(self):
    self._stop = True
    try:
      self.ws.close()
    except Exception:
      pass

results = []
for theme in ("light", "eye", "dark"):
  print("theme", theme, flush=True)
  target = new_page()
  cdp = CDP(target["webSocketDebuggerUrl"])
  cdp.send("Runtime.enable")
  cdp.send("Page.enable")
  cdp.console_errors.clear()
  cdp.page_errors.clear()
  cdp.send("Page.navigate", {"url": "http://127.0.0.1:7100/#v-strategy"})
  time.sleep(4.0)
  expr = (
    f'document.documentElement.setAttribute("data-theme","{theme}")'
    if theme != "light"
    else 'document.documentElement.removeAttribute("data-theme")'
  )
  cdp.send("Runtime.evaluate", {"expression": expr})
  time.sleep(0.5)
  info = cdp.send("Runtime.evaluate", {
    "expression": """(() => {
    location.hash = "v-strategy";
    const P = window.REITS_DATA_PANEL;
    const od = P && P.operatingDisclosedIrr;
    const host = document.getElementById("operIrrTableHost");
    const chart = document.getElementById("chartL2Operating");
    const strip = document.getElementById("operIrrPendingStrip");
    return {
      hasPanel: !!P,
      disclosed: od && od.coverage && od.coverage.disclosed,
      pending: od && od.coverage && od.coverage.pending,
      label: od && od.label,
      curve: od && od.curve && od.curve.asOf,
      feedsBanner: od && od.summary && od.summary.feedsBanner,
      tableRows: host ? host.querySelectorAll("tbody tr").length : -1,
      stripDots: strip ? strip.querySelectorAll(".oper-irr-dot").length : -1,
      chartHasCanvas: !!(chart && chart.querySelector("canvas")),
      theme: document.documentElement.getAttribute("data-theme") || "light",
      sample: (od && od.items || []).filter(r => r.code==="180201.SZ").map(r => ({code:r.code, irr:r.irrDisclosedPct, spreadBp:r.spreadBp, px:r.priceChangePct}))[0] || null
    };
  })()""",
    "returnByValue": True,
  })
  time.sleep(1.2)
  results.append({
    "theme": theme,
    "info": (info or {}).get("result", {}).get("value"),
    "consoleErrors": list(cdp.console_errors),
    "pageErrors": list(cdp.page_errors),
  })
  cdp.close()

print(json.dumps(results, ensure_ascii=False, indent=2))
bad = [r for r in results if r["consoleErrors"] or r["pageErrors"] or not (r.get("info") or {}).get("hasPanel")]
chrome.terminate()
sys.exit(1 if bad else 0)
