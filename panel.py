#!/usr/bin/env python3
"""
panel.py — Proxy Panel
Platform : Linux / Windows / Termux
Python   : 3.8+
Deps     : requests  →  pip install requests
"""

import os, sys, json, time, platform, threading, re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple, Optional

try:
    import requests
except ImportError:
    print("[!] pip install requests"); sys.exit(1)

IS_WIN    = platform.system() == "Windows"
IS_TERMUX = "com.termux" in os.environ.get("PREFIX", "")
PANEL_DIR = Path.home() / ".proxy_panel"
CONFIG_F  = PANEL_DIR / "config.json"
ENV_FILE  = PANEL_DIR / "proxy_env.sh"
PANEL_DIR.mkdir(parents=True, exist_ok=True)

COUNTRIES: Dict[str, str] = {
    "US":"United States","DE":"Germany","FR":"France","GB":"United Kingdom",
    "NL":"Netherlands","BR":"Brazil","JP":"Japan","CA":"Canada","AU":"Australia",
    "IN":"India","RU":"Russia","KR":"South Korea","SG":"Singapore","IT":"Italy",
    "ES":"Spain","SE":"Sweden","NO":"Norway","CH":"Switzerland","PL":"Poland",
    "TR":"Turkey","MX":"Mexico","AR":"Argentina","ZA":"South Africa","HK":"Hong Kong",
    "TW":"Taiwan","UA":"Ukraine","PH":"Philippines","TH":"Thailand","VN":"Vietnam",
    "ID":"Indonesia","MY":"Malaysia","CN":"China","RO":"Romania","CZ":"Czech Republic",
    "SK":"Slovakia","HU":"Hungary","BG":"Bulgaria","GR":"Greece","PT":"Portugal",
    "FI":"Finland","DK":"Denmark","AT":"Austria","BE":"Belgium","IR":"Iran",
    "PK":"Pakistan","BD":"Bangladesh","EG":"Egypt","NG":"Nigeria","KE":"Kenya",
}

DEFAULT_CFG: dict = {
    "active": False,
    "current_proxy": None,
    "current_country": None,
    "proxies": {},
    "custom": [],
    "last_fetch": {},
    "timeout": 5,
    "auto_rotate": False,
    "rotate_interval": 300,
    "test_url": "http://httpbin.org/ip",
}

# ─── ANSI ──────────────────────────────────────────────────
R   = "\033[0m"
B   = "\033[1m"
DIM = "\033[2m"
GRN = "\033[32m"
RED = "\033[31m"
YLW = "\033[33m"
CYN = "\033[36m"
WHT = "\033[97m"
MGT = "\033[35m"
CLR = "\033[2J\033[H"

def strip_ansi(s: str) -> str:
    return re.sub(r'\033\[[0-9;]*m', '', s)

def W(): return 58

def _top():     return "╔" + "═"*(W()-2) + "╗"
def _bot():     return "╚" + "═"*(W()-2) + "╝"
def _div():     return "╠" + "═"*(W()-2) + "╣"
def _row(s=""):
    vis = len(strip_ansi(s))
    pad = W() - 4 - vis
    return f"{CYN}║{R} {s}{' '*max(0,pad)} {CYN}║{R}"

# ─── Config ────────────────────────────────────────────────
def load() -> dict:
    if CONFIG_F.exists():
        try:
            cfg = json.loads(CONFIG_F.read_text())
            for k, v in DEFAULT_CFG.items():
                cfg.setdefault(k, v)
            return cfg
        except Exception:
            pass
    return DEFAULT_CFG.copy()

def save(cfg: dict) -> None:
    CONFIG_F.write_text(json.dumps(cfg, indent=2))

# ─── Proxy Fetch ───────────────────────────────────────────
def fetch_proxies(cc: str, proto: str = "http", timeout: int = 10) -> List[dict]:
    url = (
        f"https://api.proxyscrape.com/v2/?request=getproxies"
        f"&protocol={proto}&country={cc}&ssl=all&anonymity=all&simplified=true"
    )
    proxies: List[dict] = []
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            for line in r.text.strip().splitlines():
                line = line.strip()
                if ":" in line:
                    ip, port = line.rsplit(":", 1)
                    if port.isdigit():
                        proxies.append({"ip": ip, "port": int(port), "type": proto, "cc": cc})
    except Exception:
        pass
    if not proxies and proto == "http":
        return fetch_proxies(cc, "socks5", timeout)
    return proxies[:60]

def test_proxy(proxy: dict, test_url: str, timeout: int) -> Tuple[dict, float]:
    ptype = proxy["type"]
    addr  = f"{proxy['ip']}:{proxy['port']}"
    px    = {
        "http":  f"{ptype}://{addr}",
        "https": f"{ptype}://{addr}",
    }
    try:
        t0 = time.time()
        r = requests.get(test_url, proxies=px, timeout=timeout)
        if r.status_code == 200:
            return proxy, round((time.time() - t0) * 1000, 1)
    except Exception:
        pass
    return proxy, -1.0

def rank_proxies(proxies: List[dict], test_url: str, timeout: int, top_n: int = 5) -> List[Tuple[dict, float]]:
    results: List[Tuple[dict, float]] = []
    with ThreadPoolExecutor(max_workers=25) as ex:
        futs = {ex.submit(test_proxy, p, test_url, timeout): p for p in proxies[:40]}
        for fut in as_completed(futs):
            p, lat = fut.result()
            if lat > 0:
                results.append((p, lat))
    results.sort(key=lambda x: x[1])
    return results[:top_n]

# ─── System proxy set/clear ────────────────────────────────
def proxy_url(p: dict) -> str:
    return f"{p['type']}://{p['ip']}:{p['port']}"

def _write_env(url: str, cc: str) -> None:
    lines = [
        f'export http_proxy="{url}"',
        f'export https_proxy="{url}"',
        f'export HTTP_PROXY="{url}"',
        f'export HTTPS_PROXY="{url}"',
        f'export all_proxy="{url}"',
        f'export PROXY_COUNTRY="{cc}"',
    ]
    ENV_FILE.write_text("\n".join(lines) + "\n")

def _write_env_clear() -> None:
    lines = [f"unset {v}" for v in
             ["http_proxy","https_proxy","HTTP_PROXY","HTTPS_PROXY","all_proxy","PROXY_COUNTRY"]]
    ENV_FILE.write_text("\n".join(lines) + "\n")

def set_system_proxy(p: dict) -> None:
    url = proxy_url(p)
    cc  = p.get("cc", "??")
    for k in ["http_proxy","https_proxy","HTTP_PROXY","HTTPS_PROXY","all_proxy"]:
        os.environ[k] = url
    _write_env(url, cc)
    if IS_WIN:
        _win_set(p)

def clear_system_proxy() -> None:
    for k in ["http_proxy","https_proxy","HTTP_PROXY","HTTPS_PROXY","all_proxy","PROXY_COUNTRY"]:
        os.environ.pop(k, None)
    _write_env_clear()
    if IS_WIN:
        _win_clear()

def _win_set(p: dict) -> None:
    try:
        import winreg, ctypes
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            0, winreg.KEY_WRITE)
        winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "ProxyServer", 0, winreg.REG_SZ, f"{p['ip']}:{p['port']}")
        winreg.CloseKey(k)
        ctypes.windll.Wininet.InternetSetOptionW(0, 39, 0, 0)
        ctypes.windll.Wininet.InternetSetOptionW(0, 37, 0, 0)
    except Exception:
        pass

def _win_clear() -> None:
    try:
        import winreg, ctypes
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            0, winreg.KEY_WRITE)
        winreg.SetValueEx(k, "ProxyEnable", 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(k)
        ctypes.windll.Wininet.InternetSetOptionW(0, 39, 0, 0)
        ctypes.windll.Wininet.InternetSetOptionW(0, 37, 0, 0)
    except Exception:
        pass

# ─── TUI Panel ─────────────────────────────────────────────
class Panel:
    def __init__(self) -> None:
        self.cfg        = load()
        self.msg        = ""
        self._rot_thread: Optional[threading.Thread] = None

    def cls(self) -> None:
        print(CLR, end="", flush=True)

    def _lat_str(self, lat: float) -> str:
        if lat < 0:    return f"{DIM}---{R}"
        if lat < 150:  return f"{GRN}{lat:.0f}ms{R}"
        if lat < 400:  return f"{YLW}{lat:.0f}ms{R}"
        return f"{RED}{lat:.0f}ms{R}"

    def _dot(self) -> str:
        if self.cfg["active"]:
            return f"{GRN}{B}●{R} {GRN}ACTIVE{R}"
        return f"{RED}●{R} {DIM}INACTIVE{R}"

    # ── render ─────────────────────────────────────────────
    def draw(self) -> None:
        self.cls()
        cfg = self.cfg
        p   = cfg.get("current_proxy")
        cc  = cfg.get("current_country") or "--"
        lat = p.get("latency", -1) if p else -1

        print(f"{CYN}{_top()}{R}")
        # title
        title = f"{B}{WHT}PROXY PANEL{R}"
        pad   = (W() - 4 - len("PROXY PANEL")) // 2
        print(_row(" " * pad + title))
        print(f"{CYN}{_div()}{R}")

        # status
        dot = self._dot()
        cc_s = f"{B}{CYN}[{cc}]{R}"
        lat_s = self._lat_str(lat)
        print(_row(f"{dot}  {cc_s}  {lat_s}"))

        if p:
            addr = f"{DIM}{p['ip']}:{p['port']}  {p['type']}{R}"
            print(_row(f"  {addr}"))
        else:
            print(_row(f"  {DIM}no proxy configured{R}"))

        print(f"{CYN}{_div()}{R}")

        rot = f"{GRN}ON{R}" if cfg.get("auto_rotate") else f"{DIM}OFF{R}"
        menu = [
            ("1", "Activate / Deactivate"),
            ("2", f"Switch Country  {DIM}fast{R}"),
            ("3", "Refresh & Re-test Proxies"),
            ("4", "Add Custom Proxy"),
            ("5", f"Auto-Rotate  [{rot}]"),
            ("6", "Browse Proxy List"),
            ("7", "Export ENV  →  shell"),
            ("q", "Quit"),
        ]
        for key, label in menu:
            k = f"{YLW}[{key}]{R}"
            print(_row(f"  {k}  {label}"))

        print(f"{CYN}{_bot()}{R}")

        if self.msg:
            print(f"\n  {self.msg}")
            self.msg = ""

    def ask(self, prompt: str = "  → ") -> str:
        try:
            return input(f"\n{CYN}{prompt}{R}").strip()
        except (KeyboardInterrupt, EOFError):
            return "q"

    # ── actions ────────────────────────────────────────────
    def toggle(self) -> None:
        if self.cfg["active"]:
            clear_system_proxy()
            self.cfg["active"] = False
            self.cfg["current_proxy"] = None
            self.cfg["current_country"] = None
            save(self.cfg)
            self.msg = f"{RED}● Proxy deactivated{R}"
        else:
            p = self.cfg.get("current_proxy")
            if not p:
                self.msg = f"{YLW}Configure a proxy first — option [2]{R}"
                return
            set_system_proxy(p)
            self.cfg["active"] = True
            save(self.cfg)
            self.msg = f"{GRN}● Proxy active  →  {p['ip']}:{p['port']}{R}"

    def switch_country(self) -> None:
        self.cls()
        print(f"{CYN}{_top()}{R}")
        print(_row(f"{B}SWITCH COUNTRY{R}"))
        print(f"{CYN}{_div()}{R}")
        cached = sorted(self.cfg["proxies"].keys())
        if cached:
            print(_row(f"{DIM}cached: {', '.join(cached)}{R}"))
        print(_row(f"  enter code  {DIM}(e.g. US DE BR JP){R}"))
        print(_row(f"  or type {YLW}LIST{R} for full list"))
        print(f"{CYN}{_bot()}{R}")

        cc = self.ask("  country → ").upper()
        if not cc or cc == "Q":
            return
        if cc == "LIST":
            self._country_list(); return
        if cc not in COUNTRIES:
            self.msg = f"{RED}Unknown code: {cc}{R}"; return
        self._switch_to(cc)

    def _country_list(self) -> None:
        self.cls()
        print(f"{CYN}{_top()}{R}")
        print(_row(f"{B}COUNTRY LIST{R}"))
        print(f"{CYN}{_div()}{R}")
        items = list(COUNTRIES.items())
        for i in range(0, len(items), 2):
            pair = items[i:i+2]
            a = f"{YLW}{pair[0][0]}{R}  {pair[0][1]}"
            b = f"  {YLW}{pair[1][0]}{R}  {pair[1][1]}" if len(pair) > 1 else ""
            vis_a = len(pair[0][0]) + 2 + len(pair[0][1])
            pad   = max(0, 26 - vis_a)
            print(_row(f"  {a}{' '*pad}{b}"))
        print(f"{CYN}{_bot()}{R}")
        cc = self.ask("  pick → ").upper()
        if cc and cc in COUNTRIES:
            self._switch_to(cc)

    def _switch_to(self, cc: str) -> None:
        print(f"\n  {YLW}fetching {cc}...{R}", flush=True)
        last     = self.cfg["last_fetch"].get(cc, 0)
        stale    = time.time() - last > 600
        cached   = self.cfg["proxies"].get(cc)

        if stale or not cached:
            proxies = fetch_proxies(cc)
            if not proxies:
                self.msg = f"{RED}No proxies found for {cc}{R}"; return
            self.cfg["proxies"][cc] = proxies
            self.cfg["last_fetch"][cc] = time.time()
            save(self.cfg)
        else:
            proxies = cached

        print(f"  {YLW}testing {min(len(proxies),40)} proxies...{R}", flush=True)
        ranked = rank_proxies(proxies, self.cfg["test_url"], self.cfg["timeout"])

        if not ranked:
            self.msg = f"{RED}All proxies timed out for {cc}{R}"; return

        best, lat = ranked[0]
        best      = dict(best); best["latency"] = lat; best["cc"] = cc

        self.cfg["current_proxy"]   = best
        self.cfg["current_country"] = cc
        if self.cfg["active"]:
            set_system_proxy(best)
        save(self.cfg)
        self.msg = f"{GRN}→ {cc}  {best['ip']}:{best['port']}  {lat:.0f}ms{R}"

    def refresh(self) -> None:
        cc = self.cfg.get("current_country")
        if not cc:
            cc = self.ask("  country → ").upper()
            if not cc or cc not in COUNTRIES:
                self.msg = f"{YLW}Set a country first{R}"; return
        print(f"\n  {YLW}fetching {cc}...{R}", flush=True)
        proxies = fetch_proxies(cc)
        if not proxies:
            self.msg = f"{RED}Fetch failed for {cc}{R}"; return
        self.cfg["proxies"][cc]         = proxies
        self.cfg["last_fetch"][cc]      = time.time()
        print(f"  {YLW}testing...{R}", flush=True)
        ranked = rank_proxies(proxies, self.cfg["test_url"], self.cfg["timeout"])
        if ranked:
            best, lat = ranked[0]
            best = dict(best); best["latency"] = lat; best["cc"] = cc
            self.cfg["current_proxy"] = best
            if self.cfg["active"]:
                set_system_proxy(best)
            self.msg = f"{GRN}Best: {best['ip']}:{best['port']}  {lat:.0f}ms{R}"
        else:
            self.msg = f"{RED}No live proxies for {cc}{R}"
        save(self.cfg)

    def add_custom(self) -> None:
        self.cls()
        print(f"\n  {CYN}Add Custom Proxy{R}\n")
        ip    = self.ask("  IP       → ")
        port  = self.ask("  Port     → ")
        ptype = self.ask("  Protocol (http/socks5) → ").lower() or "http"
        cc    = self.ask("  Country code (opt)     → ").upper() or "??"

        if not ip or not port.isdigit():
            self.msg = f"{RED}Invalid input{R}"; return

        proxy = {"ip": ip, "port": int(port), "type": ptype, "cc": cc}
        print(f"\n  {YLW}testing...{R}", flush=True)
        _, lat = test_proxy(proxy, self.cfg["test_url"], self.cfg["timeout"])

        if lat < 0:
            ans = self.ask(f"  {RED}no response{R}  add anyway? (y/n) → ")
            if ans.lower() != "y": return
        else:
            proxy["latency"] = lat
            print(f"  {GRN}alive — {lat:.0f}ms{R}")

        self.cfg["custom"].append(proxy)
        self.cfg["current_proxy"]   = proxy
        self.cfg["current_country"] = cc
        if self.cfg["active"]:
            set_system_proxy(proxy)
        save(self.cfg)
        self.msg = f"{GRN}Custom proxy set{R}"

    def toggle_rotate(self) -> None:
        self.cfg["auto_rotate"] = not self.cfg["auto_rotate"]
        save(self.cfg)
        if self.cfg["auto_rotate"]:
            self.msg = f"{GRN}Auto-rotate ON  (every {self.cfg['rotate_interval']}s){R}"
            t = threading.Thread(target=self._rotate_loop, daemon=True)
            t.start()
            self._rot_thread = t
        else:
            self.msg = f"{YLW}Auto-rotate OFF{R}"

    def _rotate_loop(self) -> None:
        iv = self.cfg.get("rotate_interval", 300)
        while self.cfg.get("auto_rotate"):
            time.sleep(iv)
            cc = self.cfg.get("current_country")
            if cc and self.cfg.get("active"):
                self._switch_to(cc)
            self.cfg = load()

    def browse_list(self) -> None:
        self.cls()
        cc      = self.cfg.get("current_country")
        proxies = self.cfg["proxies"].get(cc, []) if cc else []
        cur     = self.cfg.get("current_proxy")

        print(f"{CYN}{_top()}{R}")
        print(_row(f"{B}PROXY LIST  {DIM}{cc or 'no country'}{R}"))
        print(f"{CYN}{_div()}{R}")

        if not proxies:
            print(_row(f"  {DIM}nothing cached — run [3] to fetch{R}"))
        else:
            for i, p in enumerate(proxies[:20]):
                lat   = p.get("latency", -1)
                mark  = f"{GRN}▶{R}" if p.get("ip") == (cur or {}).get("ip") else " "
                lat_s = self._lat_str(lat)
                row   = f"  {mark} {i+1:>2}. {p['ip']}:{p['port']}  [{p['type']}]  {lat_s}"
                print(_row(row))

        print(f"{CYN}{_bot()}{R}")
        input(f"\n  {DIM}enter to continue{R}")

    def export_env(self) -> None:
        p = self.cfg.get("current_proxy")
        if not p:
            self.msg = f"{YLW}No proxy configured{R}"; return
        url = proxy_url(p)
        _write_env(url, p.get("cc", "??"))
        self.cls()
        print(f"\n  {GRN}written:{R}  {ENV_FILE}\n")
        print(f"  {CYN}source in bash:{R}\n")
        print(f"    source {ENV_FILE}\n")
        print(f"  {CYN}or one-liner:{R}\n")
        print(f"    eval $(python3 panel.py --export)\n")
        input(f"  {DIM}enter to continue{R}")

    # ── main loop ──────────────────────────────────────────
    def run(self) -> None:
        dispatch = {
            "1": self.toggle,
            "2": self.switch_country,
            "3": self.refresh,
            "4": self.add_custom,
            "5": self.toggle_rotate,
            "6": self.browse_list,
            "7": self.export_env,
        }
        while True:
            self.draw()
            key = self.ask()
            if key == "q":
                print(f"\n  {DIM}closed. proxy state preserved in {CONFIG_F}{R}\n")
                break
            if key in dispatch:
                dispatch[key]()

# ─── CLI quick-access ──────────────────────────────────────
def cli(argv: List[str]) -> None:
    cfg = load()
    cmd = argv[1].lower()

    if cmd == "--on":
        p = cfg.get("current_proxy")
        if not p: print("[!] No proxy configured. Open panel first."); return
        set_system_proxy(p); cfg["active"] = True; save(cfg)
        print(f"[+] ON  {p['ip']}:{p['port']}  [{cfg.get('current_country','??')}]")

    elif cmd == "--off":
        clear_system_proxy(); cfg["active"] = False; save(cfg)
        print("[+] OFF")

    elif cmd == "--status":
        st = "ACTIVE" if cfg["active"] else "INACTIVE"
        p  = cfg.get("current_proxy")
        cc = cfg.get("current_country", "--")
        print(f"Status  : {st}")
        print(f"Country : {cc}")
        if p:
            print(f"Proxy   : {p['ip']}:{p['port']}  [{p['type']}]")
            print(f"Latency : {p.get('latency','?')}ms")

    elif cmd in ("--country", "-c") and len(argv) > 2:
        cc = argv[2].upper()
        if cc not in COUNTRIES: print(f"[!] Unknown: {cc}"); return
        panel = Panel(); panel._switch_to(cc)
        if panel.msg:
            print(strip_ansi(panel.msg))

    elif cmd == "--export":
        p = cfg.get("current_proxy")
        if not p: print("# no proxy configured"); return
        url = proxy_url(p)
        cc  = p.get("cc", "??")
        for line in [
            f'export http_proxy="{url}"',
            f'export https_proxy="{url}"',
            f'export HTTP_PROXY="{url}"',
            f'export HTTPS_PROXY="{url}"',
            f'export all_proxy="{url}"',
            f'export PROXY_COUNTRY="{cc}"',
        ]:
            print(line)

    elif cmd in ("--help", "-h"):
        print("""
proxy panel — quick CLI

  python3 panel.py                  interactive TUI
  python3 panel.py --on             activate saved proxy
  python3 panel.py --off            deactivate
  python3 panel.py --status         current state
  python3 panel.py --country US     fetch + switch to US
  python3 panel.py --export         print env vars

  bash one-liner:
    eval $(python3 panel.py --export)
""")
    else:
        print(f"[!] unknown: {cmd}  →