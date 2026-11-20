#!/usr/bin/env python3
# Arco Optimizer: painel de otimizacao para Windows e macOS.
# Precisa so do Python 3.9+ com Tkinter (ja vem no instalador de python.org).
import csv, ctypes, os, platform, shutil, subprocess, tempfile, threading, time
import tkinter as tk
from tkinter import messagebox

IS_WIN = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"

# ---- Tema (preto e branco). Troque ACC para dar uma cor ao painel, ex.: "#7b5cff" ----
BG, SIDE, CARD, LINE = "#000000", "#0a0a0a", "#141414", "#2a2a2a"
FG, MUTE, ACC, ACC_FG = "#ffffff", "#8c8c8c", "#ffffff", "#000000"
FONT = "Segoe UI" if IS_WIN else "Helvetica Neue"


def fmt(b):
    if b >= 1 << 30: return f"{b / (1 << 30):.2f} GB"
    if b >= 1 << 20: return f"{b / (1 << 20):.1f} MB"
    return f"{b / 1024:.0f} KB"


def sh(cmd):
    kw = {"creationflags": 0x08000000} if IS_WIN else {}  # sem janela de console
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, **kw)
        return r.returncode, r.stdout
    except Exception as e:
        return 1, str(e)


# ---------------------------------------------------------------- limpeza
def paths_for(group):
    h = os.path.expanduser("~")
    if IS_WIN:
        L = os.environ.get("LOCALAPPDATA", "")
        W = os.environ.get("WINDIR", r"C:\Windows")
        g = {
            "temp": [(os.environ.get("TEMP", tempfile.gettempdir()), "", 24), (os.path.join(W, "Temp"), "", 24)],
            "browser": [(os.path.join(L, r"Google\Chrome\User Data\Default\Cache"), "", 0),
                        (os.path.join(L, r"Microsoft\Edge\User Data\Default\Cache"), "", 0)],
            "apps": [(os.path.join(L, r"Microsoft\Windows\Explorer"), "thumbcache_", 0),
                     (os.path.join(L, "CrashDumps"), "", 0)],
        }
    else:
        g = {
            "temp": [(os.path.join(h, "Library/Logs"), "", 0)],
            "browser": [(os.path.join(h, "Library/Caches/Google/Chrome"), "", 0),
                        (os.path.join(h, "Library/Caches/com.apple.Safari"), "", 0),
                        (os.path.join(h, "Library/Caches/Firefox"), "", 0)],
            "apps": [(os.path.join(h, "Library/Caches"), "", 0),
                     (os.path.join(h, "Library/Developer/Xcode/DerivedData"), "", 0)],
        }
    return g[group]


def scan(group, only_old):
    """Lista (caminho, tamanho) dos arquivos que podem ser apagados."""
    out = []
    now = time.time()
    for base, prefix, hours in paths_for(group):
        if not os.path.isdir(base): continue
        limit = now - hours * 3600 if (hours and only_old) else now + 1
        for root, _, files in os.walk(base):
            for n in files:
                if prefix and not n.startswith(prefix): continue
                p = os.path.join(root, n)
                try:
                    st = os.lstat(p)
                    if st.st_mtime < limit: out.append((p, st.st_size))
                except OSError:
                    pass
    return out


def delete(files):
    freed = 0
    dirs = set()
    for p, s in files:
        try:
            os.remove(p); freed += s; dirs.add(os.path.dirname(p))
        except OSError:
            pass  # arquivo em uso: ignorado de proposito
    for d in sorted(dirs, key=len, reverse=True):
        try: os.rmdir(d)
        except OSError: pass
    return freed


# ---------------------------------------------------------------- sistema
class _MS(ctypes.Structure):
    _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("tot", ctypes.c_ulonglong),
                ("avail", ctypes.c_ulonglong), ("a", ctypes.c_ulonglong), ("b", ctypes.c_ulonglong),
                ("c", ctypes.c_ulonglong), ("d", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]


def mem_info():
    """(total, disponivel) em bytes."""
    try:
        if IS_WIN:
            m = _MS(); m.l = ctypes.sizeof(m)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.tot, m.avail
        total = int(sh(["sysctl", "-n", "hw.memsize"])[1].strip())
        out = sh(["vm_stat"])[1]
        page = int(out.split("page size of")[1].split("bytes")[0])
        v = {l.split(":")[0]: int(l.split(":")[1].strip(" .")) for l in out.splitlines()[1:] if ":" in l}
        pages = v.get("Pages free", 0) + v.get("Pages inactive", 0) + v.get("Pages speculative", 0)
        return total, pages * page
    except Exception:
        return 0, 0


def top_procs(n=5):
    res = []
    try:
        if IS_WIN:
            for row in csv.reader(sh(["tasklist", "/fo", "csv", "/nh"])[1].splitlines()):
                if len(row) >= 5:
                    kb = int("".join(c for c in row[4] if c.isdigit()) or 0)
                    res.append((row[0], kb * 1024))
        else:
            for line in sh(["ps", "-Ao", "rss=,comm=", "-m"])[1].splitlines()[:n * 3]:
                parts = line.strip().split(None, 1)
                if len(parts) == 2: res.append((os.path.basename(parts[1]), int(parts[0]) * 1024))
    except Exception:
        pass
    return sorted(res, key=lambda x: -x[1])[:n]


def trim_memory():
    k, p = ctypes.windll.kernel32, ctypes.windll.psapi
    k.OpenProcess.restype = ctypes.c_void_p
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    p.EmptyWorkingSet.argtypes = [ctypes.c_void_p]
    arr = (ctypes.c_ulong * 4096)(); n = ctypes.c_ulong()
    p.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(n))
    for pid in arr[: n.value // 4]:
        h = k.OpenProcess(0x0100 | 0x0400, False, pid)
        if h:
            p.EmptyWorkingSet(h); k.CloseHandle(h)


def startup_items():
    if IS_WIN:
        _, o = sh(["powershell", "-NoProfile", "-Command",
                   "Get-CimInstance Win32_StartupCommand | Select-Object -ExpandProperty Name -Unique"])
        return [l.strip() for l in o.splitlines() if l.strip()]
    _, o = sh(["osascript", "-e", 'tell application "System Events" to get the name of every login item'])
    return [i.strip() for i in o.split(",") if i.strip()]


# ---------------------------------------------------------------- tarefas dos cards
def clean_task(group):
    def run(app):
        files = scan(group, app.only_old.get())
        total = sum(s for _, s in files)
        if not files:
            return "Nada para limpar"
        if app.confirm.get() and not app.skip_confirm:
            if not app.ask(f"Apagar {len(files)} arquivos ({fmt(total)})?\n\nArquivos em uso serão ignorados."):
                return "Cancelado"
        freed = delete(files)
        app.freed_total += freed
        return f"{fmt(freed)} liberados"
    return run


def trash_task(app):
    if IS_WIN:
        ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x7)
        return "Lixeira esvaziada"
    trash = os.path.expanduser("~/.Trash")
    files = [(os.path.join(r, n), 0) for r, _, fs in os.walk(trash) for n in fs]
    if not files: return "Lixeira já estava vazia"
    if app.confirm.get() and not app.skip_confirm and not app.ask(f"Esvaziar a Lixeira ({len(files)} arquivos)?"):
        return "Cancelado"
    for item in os.listdir(trash):
        p = os.path.join(trash, item)
        shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.path.exists(p) and os.remove(p)
    return "Lixeira esvaziada"


def memory_task(app):
    total, before = mem_info()
    if IS_WIN:
        trim_memory(); time.sleep(1.0)
        _, after = mem_info()
        gain = max(0, after - before)
        app.log(f"Memória livre: {fmt(before)} → {fmt(after)} de {fmt(total)}")
        res = f"+{fmt(gain)} livres"
    else:
        app.log(f"Memória disponível: {fmt(before)} de {fmt(total)} (o macOS gerencia a RAM sozinho)")
        res = f"{fmt(before)} disponíveis"
    for name, b in top_procs():
        app.log(f"   {name:<28} {fmt(b)}")
    return res


def dns_task(app):
    cmd = ["ipconfig", "/flushdns"] if IS_WIN else ["dscacheutil", "-flushcache"]
    code, _ = sh(cmd)
    return "Cache DNS limpo" if code == 0 else "Não foi possível limpar"


def power_task(app):
    code, _ = sh(["powercfg", "/setactive", "SCHEME_MIN"])
    return "Alto desempenho ativado" if code == 0 else "Falhou (tente como administrador)"


def startup_task(app):
    items = startup_items()
    app.log("Programas que iniciam com o sistema:")
    for i in items: app.log(f"   {i}")
    app.log("Para desligar: " + ("Gerenciador de Tarefas > Inicializar." if IS_WIN
                                 else "Ajustes do Sistema > Geral > Itens de Login."))
    return f"{len(items)} programas listados"


CARDS = {
    "Limpeza": [
        ("temp", "Arquivos temporários", "Remove temporários e logs antigos que o sistema deixou para trás.", clean_task("temp"), True),
        ("browser", "Cache do navegador", "Limpa o cache do Chrome, Edge, Safari e Firefox. Senhas e histórico ficam.", clean_task("browser"), True),
        ("apps", "Cache de apps", "Miniaturas, relatórios de erro e caches de programas.", clean_task("apps"), True),
        ("trash", "Lixeira", "Esvazia a Lixeira para devolver o espaço ao disco.", trash_task, True),
    ],
    "Sistema": [
        ("mem", "Memória", "Libera RAM de programas parados e mostra quem mais consome.", memory_task, True),
        ("dns", "Rede", "Limpa o cache DNS. Ajuda quando sites não abrem ou carregam lento.", dns_task, True),
        ("pow", "Energia", "Ativa o plano de alto desempenho do Windows.", power_task, IS_WIN),
        ("start", "Inicialização", "Lista os programas que abrem junto com o sistema.", startup_task, True),
    ],
}
RUN_ALL = ["temp", "browser", "apps", "trash", "mem", "dns"]


# ---------------------------------------------------------------- interface
class Card(tk.Frame):
    def __init__(self, parent, app, cid, title, desc, fn, enabled):
        super().__init__(parent, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        self.app, self.cid, self.title, self.fn, self.enabled = app, cid, title, fn, enabled
        tk.Frame(self, bg=ACC if enabled else LINE, width=3).pack(side="left", fill="y")
        body = tk.Frame(self, bg=CARD); body.pack(side="left", fill="both", expand=True, padx=14, pady=12)
        tk.Label(body, text=title, bg=CARD, fg=FG, font=(FONT, 12, "bold"), anchor="w").pack(fill="x")
        tk.Label(body, text=desc if enabled else "Disponível apenas no Windows.", bg=CARD, fg=MUTE,
                 font=(FONT, 9), anchor="w", justify="left", wraplength=290).pack(fill="x", pady=(2, 4))
        self.status = tk.Label(body, text="", bg=CARD, fg=FG, font=(FONT, 9, "bold"), anchor="w")
        self.status.pack(fill="x")
        self.btn = tk.Canvas(self, width=40, height=40, bg=CARD, highlightthickness=0,
                             cursor="hand2" if enabled else "arrow")
        self.circle = self.btn.create_oval(3, 3, 37, 37, fill=ACC if enabled else LINE, outline="")
        self.tri = self.btn.create_polygon(16, 12, 16, 28, 29, 20, fill=ACC_FG if enabled else MUTE)
        self.btn.pack(side="right", padx=14)
        if enabled:
            self.btn.bind("<Button-1>", lambda e: app.run_card(self))
            self.btn.bind("<Enter>", lambda e: self.btn.itemconfig(self.circle, fill="#cfcfcf"))
            self.btn.bind("<Leave>", lambda e: self.btn.itemconfig(self.circle, fill=ACC))

    def set_busy(self, busy):
        self.btn.itemconfig(self.tri, state="hidden" if busy else "normal")
        if busy: self.status.config(text="Executando…")


class App:
    def __init__(self, root):
        self.root = root
        root.title("Arco Optimizer"); root.configure(bg=BG); root.geometry("1040x720"); root.minsize(900, 640)
        self.confirm = tk.BooleanVar(value=True)
        self.only_old = tk.BooleanVar(value=True)
        self.skip_confirm = False
        self.freed_total = 0
        self.busy = False
        self.cards = {}

        side = tk.Frame(root, bg=SIDE, width=96); side.pack(side="left", fill="y"); side.pack_propagate(False)
        tk.Label(side, text="arco", bg=SIDE, fg=FG, font=(FONT, 15, "bold")).pack(pady=(22, 26))
        self.navs = {}
        for key, glyph, name in (("home", "⌂", "Início"), ("opt", "✦", "Otimizações"), ("cfg", "⚙", "Config.")):
            f = tk.Frame(side, bg=SIDE, cursor="hand2"); f.pack(fill="x", pady=4)
            bar = tk.Frame(f, bg=SIDE, width=3); bar.pack(side="left", fill="y")
            inner = tk.Frame(f, bg=SIDE); inner.pack(side="left", expand=True, pady=8)
            g = tk.Label(inner, text=glyph, bg=SIDE, fg=MUTE, font=(FONT, 18))
            t = tk.Label(inner, text=name, bg=SIDE, fg=MUTE, font=(FONT, 8))
            g.pack(); t.pack()
            for w in (f, inner, g, t): w.bind("<Button-1>", lambda e, k=key: self.show(k))
            self.navs[key] = (bar, g, t)

        main = tk.Frame(root, bg=BG); main.pack(side="left", fill="both", expand=True, padx=28, pady=22)
        self.pages = {k: tk.Frame(main, bg=BG) for k in ("home", "opt", "cfg")}
        self.build_home(); self.build_opt(); self.build_cfg()

        logf = tk.Frame(main, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        logf.pack(side="bottom", fill="x", pady=(14, 0))
        self.logbox = tk.Text(logf, height=7, bg=CARD, fg=MUTE, bd=0, font=("Consolas" if IS_WIN else "Menlo", 9),
                              state="disabled", padx=12, pady=8, wrap="word")
        self.logbox.pack(fill="x")
        self.show("home"); self.refresh(); self.log("Pronto. Escolha uma otimização ou clique em Otimizar tudo.")

    # ---- paginas
    def head(self, page, title, sub):
        tk.Label(page, text=title, bg=BG, fg=FG, font=(FONT, 24, "bold"), anchor="w").pack(fill="x")
        tk.Label(page, text=sub, bg=BG, fg=MUTE, font=(FONT, 10), anchor="w").pack(fill="x", pady=(2, 18))

    def build_home(self):
        p = self.pages["home"]
        self.head(p, "Otimize seu computador", "Veja como ele está agora e limpe tudo com um clique.")
        row = tk.Frame(p, bg=BG); row.pack(fill="x")
        self.stats = {}
        for i, (k, label) in enumerate((("disk", "Disco livre"), ("ram", "Memória disponível"), ("freed", "Liberado nesta sessão"))):
            c = tk.Frame(row, bg=CARD, highlightthickness=1, highlightbackground=LINE)
            c.grid(row=0, column=i, sticky="nsew", padx=(0, 12 if i < 2 else 0)); row.columnconfigure(i, weight=1)
            v = tk.Label(c, text="—", bg=CARD, fg=FG, font=(FONT, 20, "bold"), anchor="w"); v.pack(fill="x", padx=16, pady=(14, 0))
            tk.Label(c, text=label, bg=CARD, fg=MUTE, font=(FONT, 9), anchor="w").pack(fill="x", padx=16, pady=(0, 14))
            self.stats[k] = v
        self.allbtn = tk.Button(p, text="Otimizar tudo", command=self.run_all, bg=ACC, fg=ACC_FG, activebackground="#cfcfcf",
                                activeforeground=ACC_FG, relief="flat", bd=0, font=(FONT, 13, "bold"), padx=34, pady=12,
                                cursor="hand2", highlightthickness=0)
        self.allbtn.pack(anchor="w", pady=26)
        tk.Label(p, text="Limpa temporários, caches e Lixeira, libera memória e limpa o cache DNS.\n"
                         "Nunca apaga documentos, fotos ou programas.", bg=BG, fg=MUTE, font=(FONT, 10), anchor="w",
                 justify="left").pack(fill="x")

    def build_opt(self):
        p = self.pages["opt"]
        self.head(p, "Otimizações", "Cada rotina roda sozinha. Clique no botão de play.")
        for section, items in CARDS.items():
            tk.Label(p, text=section, bg=BG, fg=FG, font=(FONT, 11, "bold"), anchor="w").pack(fill="x", pady=(0, 8))
            grid = tk.Frame(p, bg=BG); grid.pack(fill="x", pady=(0, 14))
            grid.columnconfigure((0, 1), weight=1, uniform="c")
            for i, (cid, title, desc, fn, ok) in enumerate(items):
                c = Card(grid, self, cid, title, desc, fn, ok)
                c.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0, 12) if i % 2 == 0 else 0, pady=(0, 10))
                self.cards[cid] = c

    def build_cfg(self):
        p = self.pages["cfg"]
        self.head(p, "Configurações", "Ajuste como o Arco Optimizer trabalha.")
        for var, text in ((self.confirm, "Pedir confirmação antes de apagar arquivos"),
                          (self.only_old, "Em temporários, apagar só arquivos com mais de 24 horas (mais seguro)")):
            tk.Checkbutton(p, text=text, variable=var, bg=BG, fg=FG, selectcolor=CARD, activebackground=BG,
                           activeforeground=FG, font=(FONT, 11), anchor="w", highlightthickness=0, bd=0).pack(fill="x", pady=6)

    # ---- comportamento
    def show(self, key):
        for k, pg in self.pages.items():
            pg.pack_forget()
            bar, g, t = self.navs[k]
            on = k == key
            bar.config(bg=ACC if on else SIDE); g.config(fg=FG if on else MUTE); t.config(fg=FG if on else MUTE)
        self.pages[key].pack(side="top", fill="both", expand=True)

    def log(self, msg):
        def w():
            self.logbox.config(state="normal")
            self.logbox.insert("end", time.strftime("%H:%M  ") + msg + "\n" if not msg.startswith("   ") else msg + "\n")
            self.logbox.see("end"); self.logbox.config(state="disabled")
        self.root.after(0, w)

    def ask(self, text):
        ev, out = threading.Event(), []
        def q():
            out.append(messagebox.askyesno("Arco Optimizer", text)); ev.set()
        self.root.after(0, q); ev.wait()
        return out[0]

    def refresh(self):
        try:
            free = shutil.disk_usage(os.path.expanduser("~")).free
            self.stats["disk"].config(text=fmt(free))
            mt, ma = mem_info()
            self.stats["ram"].config(text=f"{fmt(ma)} de {fmt(mt)}" if mt else "—")
            self.stats["freed"].config(text=fmt(self.freed_total))
        except Exception:
            pass
        self.root.after(4000, self.refresh)

    def run_card(self, card):
        if self.busy: return
        self.busy = True; card.set_busy(True)
        self.log(f"Iniciando: {card.title}")
        def work():
            try: res = card.fn(self)
            except Exception as e: res = f"Erro: {e}"
            def done():
                card.set_busy(False); card.status.config(text=res); self.busy = False; self.refresh()
            self.root.after(0, done); self.log(f"{card.title}: {res}")
        threading.Thread(target=work, daemon=True).start()

    def run_all(self):
        if self.busy: return
        if not messagebox.askyesno("Arco Optimizer", "Otimizar tudo agora?\n\nSerão limpos temporários, caches e a Lixeira.\n"
                                   "Documentos, fotos e programas não são tocados."):
            return
        self.busy = True; self.skip_confirm = True; self.allbtn.config(state="disabled", text="Otimizando…")
        def work():
            for cid in RUN_ALL:
                try:
                    card = self.cards[cid]
                    self.root.after(0, lambda c=card: c.set_busy(True))
                    res = card.fn(self)
                except Exception as e:
                    res = f"Erro: {e}"
                self.root.after(0, lambda c=card, r=res: (c.set_busy(False), c.status.config(text=r)))
                self.log(f"{self.cards[cid].title}: {res}")
            def done():
                self.skip_confirm = False; self.busy = False
                self.allbtn.config(state="normal", text="Otimizar tudo"); self.refresh()
            self.root.after(0, done)
            self.log(f"Concluído. Total liberado nesta sessão: {fmt(self.freed_total)}")
        threading.Thread(target=work, daemon=True).start()


def main():
    if IS_WIN:
        try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception: pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
