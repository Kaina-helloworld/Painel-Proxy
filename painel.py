#!/usr/bin/env python3
"""
proxy_panel.py
Platform : Linux / Windows / Termux
Python   : 3.8+
Deps     : requests
"""

import os, sys, json, time, platform, threading, subprocess, socket
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
    from requests.exceptions import RequestException
except ImportError:
    print("[!] Install requests: pip install requests")
    sys.exit(1)

IS_WINDOWS = platform.system() == "Windows"
IS_TERMUX  = "com.termux" in os.environ.get("PREFIX", "")
PANEL_DIR  = Path.home() / ".proxy_panel"
CONFIG_F   = PANEL_DIR / "config.json"
ENV_FILE   = PANEL_DIR / "proxy_env.sh"
PANEL_DIR.mkdir(parents=True, exist_ok=True)

COUNTRIES = {
    "US": "United States", "DE": "Germany", "FR": "France",
    "GB": "United Kingdom", "NL": "Netherlands", "BR": "Brazil",
    "JP": "Japan", "CA": "Canada", "AU": "Australia", "IN": "India",
    "RU": "Russia", "KR": "South Korea", "SG": "Singapore",
    "IT": "Italy", "ES": "Spain", "SE": "Sweden", "NO": "Norway",
    "CH": "Switzerland", "PL": "Poland", "TR": "Turkey",
    "MX": "Mexico", "AR": "Argentina", "ZA": "South Africa",
    "HK": "Hong Kong", "TW": "Taiwan", "UA": "Ukraine",
    "PH": "Philippines", "TH": "Thailand", "VN": "Vietnam",
    "ID": "Indonesia", "MY": "Malaysia", "CN": "China",
}

DEFAULT_CFG = {
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
R  = "\033[0m"
B  = "\033[1m"
DIM = "\033[2m"
GRN = "\033[32m"
RED = "\033[31m"
YLW = "\033[33m"
CYN = "\033[36m"
MGT = "\033[35m"
BLU = "\033[34m"
WHT = "\033[37m"
CLR = "\033[2J\033[H"

def esc(code): return code if not IS_WINDOWS else ""

def box_line(content, width=54):
    return f"║ {content:<{width-4}} ║"

def divider(width=54):
    return "╠" + "═"*(width-2) + "╣"

def top(width=54):
    return "╔" + "═"*(width-2) + "╗"

def bot(width=54):
    return "╚" + "═"*(width-2) + "╝"

# ─── Config ────────────────────────────────────────────────
def load():
    if CONFIG_F.exists():
        try:
            with open(CONFIG_F) as f:
                cfg = json.load(f)
            for k, v in DEFAULT_CFG.items():
                cfg.setdefault(k, v)
            return cfg
        except:
            pass
    return DEFAULT_CFG.copy()

def save(cfg):
    with open(CONFIG_F, "w") as f:
        json.dump(cfg, f, indent=2)

# ─── Proxy Fetch ───────────────────────────────────────────
SOURCES = [
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol={proto}&country={cc}&ssl=all&anonymity=all&simplified=true",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",  # fallback all
]

def fetch_proxies(cc: str, proto="http", timeout=10) -> list[dict]:
    """Fetch proxy list for a country code."""
    url = f"https://api.proxyscrape.com/v2/?request=getproxies&protocol={proto}&country={cc}&ssl=all&anonymity=all&simplified=true"
    proxies = []
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            for line in r.text.strip().splitlines():
                line = line.strip()
                if ":" in line:
                    ip, port = line.rsplit(":", 1)
                    proxies.append({"ip": ip, "port": int(port), "type": proto, "cc": cc})
    except:
        pass
    
    # fallback: socks5
    if not proxies and proto == "http":
        proxies = fetch_proxies(cc, "socks5", timeout)
    
    return proxies[:50]  # cap at 50

def test_proxy(proxy: dict, test_url: str, timeout: int) -> tuple[dict, float]:
    """Returns (proxy, latency_ms) or (proxy, -1) on failure."""
    ptype = proxy["type"]
    addr  = f"{proxy['ip']}:{proxy['port']}"
    proxies = {
        "http":  f"{ptype}://{addr}",
        "https": f"{ptype}://{addr}",
    }
    try:
        start = time.time()
        r = requests.get(test_url, proxies=proxies, timeout=timeout)
        if r.status_code == 200:
            latency = (time.time() - start) * 1000
            return proxy, round(latency, 1)
    except:
        pass
    return proxy, -1

def best_proxy(proxies: list[dict], test_url: str, timeout: int, top_n=5) -> list[tuple]:
    """Test proxies concurrently, return top N sorted by latency."""
    results = []
    sample = proxies[:30]  # test up to 30
    with ThreadPoolExecutor(max_workers=20) as ex:
        futs = {ex.submit(test_proxy, p, test_url, timeout): p for p in sample}
        for fut in as_completed(futs):
            proxy, lat = fut.result()
            if lat > 0:
                results.append((proxy, lat))
    results.sort(key=lambda x: x[1])
    return results[:top_n]

# ─── System Proxy Set/Clear ────────────────────────────────
def proxy_url(proxy: dict) -> str:
    return f"{proxy['type']}://{proxy['ip']}:{proxy['port']}"

def set_system_proxy(proxy: dict):
    url = proxy_url(proxy)
    os.environ["http_proxy"]  = url
    os.environ["https_proxy"] = url
    os.environ["HTTP_PROXY"]  = url
    os.environ["HTTPS_PROXY"] = url
    os.environ["all_proxy"]   = url
    
    # write env file for bash sourcing
    with open(ENV_FILE, "w") as f:
        f.write(f'export http_proxy="{url}"\n')
        f.write(f'export https_proxy="{url}"\n')
        f.write(f'export HTTP_PROXY="{url}"\n')
        f.write(f'export HTTPS_PROXY="{url}"\n')
        f.write(f'export all_proxy="{url}"\n')
        f.write(f'export PROXY_COUNTRY="{proxy.get("cc","??")}"\n')
    
    if IS_WINDOWS:
        _set_windows_proxy(proxy)

def clear_system_proxy():
    for var in ["http_proxy","https_proxy","HTTP_PROXY","HTTPS_PROXY","all_proxy","PROXY_COUNTRY"]:
        os.environ.pop(var, None)
    with open(ENV_FILE, "w") as f:
        for var in ["http_proxy","https_proxy","HTTP_PROXY","HTTPS_PROXY","all_proxy","PROXY_COUNTRY"]:
            f.write(f'unset {var}\n')
    if IS_WINDOWS:
        _clear_windows_proxy()

def _set_windows_proxy(proxy: dict):
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            0, winreg.KEY_WRITE)
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ,
            f"{proxy['ip']}:{proxy['port']}")
        winreg.CloseKey(key)
        # refresh IE settings
        import ctypes
        ctypes.windll.Wininet.InternetSetOptionW(0, 39, 0, 0)  # INTERNET_OPTION_SETTINGS_CHANGED
        ctypes.windll.Wininet.InternetSetOptionW(0, 37, 0, 0)  # INTERNET_OPTION_REFRESH
    except Exception as e:
        pass

def _clear_windows_proxy():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            0, winreg.KEY_WRITE)
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(key)
        import ctypes
        ctypes.windll.Wininet.InternetSetOptionW(0, 39, 0, 0)
        ctypes.windll.Wininet.InternetSetOptionW(0, 37, 0, 0)
    except:
        pass

# ─── TUI ───────────────────────────────────────────────────
class ProxyPanel:
    def __init__(self):
        self.cfg = load()
        self.status_msg = ""
        self.working = False
        self.W = 56
    
    def cls(self):
        print(CLR if not IS_WINDOWS else "\033[2J\033[H", end="")
    
    def ping_display(self, lat):
        if lat < 0:   return f"{RED}--{R}"
        if lat < 200: return f"{GRN}{lat:.0f}ms{R}"
        if lat < 500: return f"{YLW}{lat:.0f}ms{R}"
        return f"{RED}{lat:.0f}ms{R}"
    
    def status_dot(self):
        if self.cfg["active"]:
            return f"{GRN}●{R} ACTIVE"
        return f"{RED}●{R} INACTIVE"
    
    def render_main(self):
        self.cls()
        W = self.W
        cfg = self.cfg
        
        print(f"{CYN}{top(W)}{R}")
        title = f"{B}{WHT}  PROXY PANEL  {R}"
        print(f"{CYN}║{R}{title:^{W+8}}{CYN}║{R}")
        print(f"{CYN}{divider(W)}{R}")
        
        # status line
        status = self.status_dot()
        cc = cfg.get("current_country") or "--"
        proxy = cfg.get("current_proxy")
        lat = proxy.get("latency", -1) if proxy else -1
        
        line = f" {status}  [{B}{cc}{R}]  {self.ping_display(lat)}"
        print(f"{CYN}║{R}{line:<{W+15}}{CYN}║{R}")
        
        if proxy:
            addr = f"  {DIM}{proxy['ip']}:{proxy['port']} ({proxy['type']}){R}"
            print(f"{CYN}║{R}{addr:<{W+10}}{CYN}║{R}")
        else:
            print(f"{CYN}║{R}{'  no proxy configured':<{W-2}}{CYN}║{R}")
        
        print(f"{CYN}{divider(W)}{R}")
        
        items = [
            ("[1]", "Activate / Deactivate"),
            ("[2]", "Switch Country →"),
            ("[3]", "Fetch & Test Proxies"),
            ("[4]", "Add Custom Proxy"),
            ("[5]", "Auto-Rotate " + ("ON" if cfg.get("auto_rotate") else "OFF")),
            ("[6]", "Show Proxy List"),
            ("[7]", "Export Shell ENV"),
            ("[q]", "Quit"),
        ]
        for key, label in items:
            k = f"{YLW}{key}{R}"
            print(f"{CYN}║{R}  {k}  {label:<{W-8}}{CYN}║{R}")
        
        print(f"{CYN}{bot(W)}{R}")
        
        if self.status_msg:
            print(f"\n  {self.status_msg}")
            self.status_msg = ""
        
        if self.working:
            print(f"\n  {YLW}working...{R}")
    
    def input_prompt(self, prompt="  → "):
        try:
            return input(f"\n{CYN}{prompt}{R}").strip()
        except (KeyboardInterrupt, EOFError):
            return "q"
    
    # ── Actions ────────────────────────────────────────────
    def action_toggle(self):
        if self.cfg["active"]:
            clear_system_proxy()
            self.cfg["active"] = False
            self.cfg["current_proxy"] = None
            self.cfg["current_country"] = None
            save(self.cfg)
            self.status_msg = f"{RED}● Proxy deactivated{R}"
        else:
            proxy = self.cfg.get("current_proxy")
            if not proxy:
                self.status_msg = f"{YLW}No proxy set — pick a country first [2]{R}"
                return
            set_system_proxy(proxy)
            self.cfg["active"] = True
            save(self.cfg)
            self.status_msg = f"{GRN}● Proxy activated{R}"
    
    def action_switch_country(self):
        self.render_country_menu()
    
    def render_country_menu(self):
        self.cls()
        W = self.W
        print(f"{CYN}{top(W)}{R}")
        print(f"{CYN}║{R}{'  SWITCH COUNTRY':<{W-2}}{CYN}║{R}")
        print(f"{CYN}{divider(W)}{R}")
        
        # show cached countries
        cached = list(self.cfg["proxies"].keys())
        print(f"{CYN}║{R}  {DIM}Cached:{R} {', '.join(cached) or 'none':<{W-12}}{CYN}║{R}")
        print(f"{CYN}║{R}{'':<{W-2}}{CYN}║{R}")
        print(f"{CYN}║{R}  Enter country code (e.g. US, DE, BR){' '*(W-42)}{CYN}║{R}")
        print(f"{CYN}║{R}  or type LIST to see all countries{' '*(W-38)}{CYN}║{R}")
        print(f"{CYN}{bot(W)}{R}")
        
        cc = self.input_prompt("  country → ").upper()
        
        if cc == "Q" or not cc:
            return
        
        if cc == "LIST":
            self.show_country_list()
            return
        
        if cc not in COUNTRIES:
            self.status_msg = f"{RED}Unknown country code: {cc}{R}"
            return
        
        self._switch_to(cc)
    
    def show_country_list(self):
        self.cls()
        W = self.W
        print(f"{CYN}{top(W)}{R}")
        print(f"{CYN}║{R}{'  AVAILABLE COUNTRIES':<{W-2}}{CYN}║{R}")
        print(f"{CYN}{divider(W)}{R}")
        items = list(COUNTRIES.items())
        for i in range(0, len(items), 2):
            pair = items[i:i+2]
            if len(pair) == 2:
                a = f"{YLW}{pair[0][0]}{R} {pair[0][1]}"
                b = f"{YLW}{pair[1][0]}{R} {pair[1][1]}"
                line = f"  {a:<26}  {b}"
                print(f"{CYN}║{R}{line:<{W+10}}{CYN}║{R}")
            else:
                a = f"{YLW}{pair[0][0]}{R} {pair[0][1]}"
                print(f"{CYN}║{R}  {a:<{W-4}}{CYN}║{R}")
        print(f"{CYN}{bot(W)}{R}")
        cc = self.input_prompt("  pick → ").upper()
        if cc and cc in COUNTRIES:
            self._switch_to(cc)
    
    def _switch_to(self, cc: str):
        print(f"\n  {YLW}fetching proxies for {cc}...{R}", flush=True)
        
        # check cache freshness (10 min)
        last = self.cfg["last_fetch"].get(cc, 0)
        if time.time() - last > 600 or cc not in self.cfg["proxies"] or not self.cfg["proxies"].get(cc):
            proxies = fetch_proxies(cc)
            if not proxies:
                self.status_msg = f"{RED}No proxies found for {cc}{R}"
                return
            self.cfg["proxies"][cc] = proxies
            self.cfg["last_fetch"][cc] = time.time()
            save(self.cfg)
        else:
            proxies = self.cfg["proxies"][cc]
        
        print(f"  {YLW}testing {len(proxies[:30])} proxies...{R}", flush=True)
        ranked = best_proxy(proxies, self.cfg["test_url"], self.cfg["timeout"])
        
        if not ranked:
            self.status_msg = f"{RED}All proxies failed for {cc}{R}"
            return
        
        best, lat = ranked[0]
        best["latency"] = lat
        best["cc"] = cc
        
        self.cfg["current_proxy"] = best
        self.cfg["current_country"] = cc
        
        if self.cfg["active"]:
            set_system_proxy(best)
        
        save(self.cfg)
        self.status_msg = f"{GRN}Switched to {cc} via {best['ip']}:{best['port']} ({lat:.0f}ms){R}"
    
    def action_fetch(self):
        cc = self.cfg.get("current_country")
        if not cc:
            # ask
            cc = self.input_prompt("  country code → ").upper()
            if not cc or cc not in COUNTRIES:
                self.status_msg = f"{YLW}Pick a country first{R}"
                return
        
        print(f"\n  {YLW}refreshing proxies for {cc}...{R}", flush=True)
        proxies = fetch_proxies(cc)
        if not proxies:
            self.status_msg = f"{RED}Fetch failed for {cc}{R}"
            return
        self.cfg["proxies"][cc] = proxies
        self.cfg["last_fetch"][cc] = time.time()
        
        print(f"  {YLW}testing...{R}", flush=True)
        ranked = best_proxy(proxies, self.cfg["test_url"], self.cfg["timeout"])
        if ranked:
            best, lat = ranked[0]
            best["latency"] = lat
            best["cc"] = cc
            self.cfg["current_proxy"] = best
            if self.cfg["active"]:
                set_system_proxy(best)
            self.status_msg = f"{GRN}Updated — best: {best['ip']}:{best['port']} ({lat:.0f}ms){R}"
        else:
            self.status_msg = f"{RED}No working proxies found{R}"
        save(self.cfg)
    
    def action_add_custom(self):
        self.cls()
        print(f"\n  {CYN}Add Custom Proxy{R}")
        ip   = self.input_prompt("  IP → ")
        port = self.input_prompt("  Port → ")
        ptype = self.input_prompt("  Type (http/socks5) → ").lower() or "http"
        cc   = self.input_prompt("  Country code (optional) → ").upper() or "??"
        
        try:
            proxy = {"ip": ip, "port": int(port), "type": ptype, "cc": cc}
        except ValueError:
            self.status_msg = f"{RED}Invalid port{R}"
            return
        
        print(f"\n  {YLW}testing...{R}", flush=True)
        _, lat = test_proxy(proxy, self.cfg["test_url"], self.cfg["timeout"])
        if lat < 0:
            ans = self.input_prompt(f"  {RED}Proxy didn't respond. Add anyway? (y/n){R} → ")
            if ans.lower() != "y":
                return
        else:
            proxy["latency"] = lat
            self.status_msg = f"{GRN}Proxy works — {lat:.0f}ms{R}"
        
        self.cfg["custom"].append(proxy)
        self.cfg["current_proxy"] = proxy
        self.cfg["current_country"] = cc
        if self.cfg["active"]:
            set_system_proxy(proxy)
        save(self.cfg)
    
    def action_toggle_rotate(self):
        self.cfg["auto_rotate"] = not self.cfg["auto_rotate"]
        save(self.cfg)
        state = "ON" if self.cfg["auto_rotate"] else "OFF"
        self.status_msg = f"{GRN if self.cfg['auto_rotate'] else YLW}Auto-rotate {state}{R}"
        
        if self.cfg["auto_rotate"]:
            t = threading.Thread(target=self._rotate_loop, daemon=True)
            t.start()
    
    def _rotate_loop(self):
        while self.cfg.get("auto_rotate"):
            time.sleep(self.cfg.get("rotate_interval", 300))
            cc = self.cfg.get("current_country")
            if cc and self.cfg.get("active"):
                self._switch_to(cc)
    
    def action_show_list(self):
        self.cls()
        cc = self.cfg.get("current_country")
        proxies = self.cfg["proxies"].get(cc, []) if cc else []
        
        W = self.W
        print(f"{CYN}{top(W)}{R}")
        print(f"{CYN}║{R}{'  PROXY LIST — ' + (cc or 'none'):<{W-2}}{CYN}║{R}")
        print(f"{CYN}{divider(W)}{R}")
        
        if not proxies:
            print(f"{CYN}║{R}{'  no proxies cached':<{W-2}}{CYN}║{R}")
        else:
            for i, p in enumerate(proxies[:15]):
                lat = p.get("latency", -1)
                mark = f"{GRN}*{R}" if p == self.cfg.get("current_proxy") else " "
                line = f"  {mark}{i+1:>2}. {p['ip']}:{p['port']} [{p['type']}] {self.ping_display(lat)}"
                print(f"{CYN}║{R}{line:<{W+12}}{CYN}║{R}")
        
        print(f"{CYN}{bot(W)}{R}")
        input(f"\n  {DIM}press enter{R}")
    
    def action_export_env(self):
        proxy = self.cfg.get("current_proxy")
        if not proxy:
            self.status_msg = f"{YLW}No proxy configured{R}"
            return
        url = proxy_url(proxy)
        # write env file
        with open(ENV_FILE, "w") as f:
            f.write(f'export http_proxy="{url}"\n')
            f.write(f'export https_proxy="{url}"\n')
            f.write(f'export HTTP_PROXY="{url}"\n')
            f.write(f'export HTTPS_PROXY="{url}"\n')
            f.write(f'export all_proxy="{url}"\n')
        
        self.cls()
        print(f"\n  {GRN}ENV file written:{R} {ENV_FILE}")
        print(f"\n  {CYN}Source it in your shell:{R}")
        print(f"\n    source {ENV_FILE}\n")
        print(f"  Or add to ~/.bashrc:\n")
        print(f"    source {ENV_FILE}\n")
        input(f"\n  {DIM}press enter{R}")
    
    # ── Main loop ──────────────────────────────────────────
    def run(self):
        actions = {
            "1": self.action_toggle,
            "2": self.action_switch_country,
            "3": self.action_fetch,
            "4": self.action_add_custom,
            "5": self.action_toggle_rotate,
            "6": self.action_show_list,
            "7": self.action_export_env,
        }
        
        while True:
            self.render_main()
            key = self.input_prompt()
            if key == "q":
                print(f"\n  {DIM}panel closed. proxy state preserved.{R}\n")
                break
            if key in actions:
                actions[key]()

# ─── CLI entrypoint ────────────────────────────────────────
def cli_quick(args):
    """Fast CLI for bash integration."""
    cfg = load()
    cmd = args[1].lower()
    
    if cmd == "--on":
        proxy = cfg.get("current_proxy")
        if not proxy:
            print("[!] No proxy configured. Run panel first."); return
        set_system_proxy(proxy)
        cfg["active"] = True; save(cfg)
        print(f"[+] Proxy ON — {proxy['ip']}:{proxy['port']} [{cfg.get('current_country','??')}]")
    
    elif cmd == "--off":
        clear_system_proxy