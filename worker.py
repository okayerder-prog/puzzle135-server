#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PUZZLE135 — Universal Worker v5.0
Windows / Linux / Mac / Android / Her GPU
Intel / AMD / NVIDIA / Apple Silicon
CUDA gerekmez — Vulkan/DX12/Metal otomatik
"""

import os, sys, time, json, threading, subprocess, platform, re
import urllib.request, urllib.error, atexit, signal

# ── CONFIG (sunucu inject eder) ───────────────────────────
WAX_ACCOUNT   = "__WAX_ACCOUNT__"
POOL_URL      = "__POOL_URL__"
VERSION       = "5.0.0"
PUBKEY        = "02145d2611c823a396ef6712ce0f712f09b9b4f3135e3e0aa3230fb9b6d08d1e16"
RANGE_START   = "4000000000000000000000000000000000"
RANGE_BITS    = "135"
REPORT_SECS   = 30
NFT_THRESHOLD = 10000

# ── PLATFORM ──────────────────────────────────────────────
SYS    = platform.system()   # Windows / Linux / Darwin
ARCH   = platform.machine()  # x86_64 / aarch64 / arm64
IS_WIN = SYS == "Windows"
IS_MAC = SYS == "Darwin"
IS_LIN = SYS == "Linux"

if IS_WIN: os.system("color")

R="\033[0m";G="\033[92m";Y="\033[93m";RE="\033[91m"
C="\033[96m";M="\033[95m";W="\033[97m";BD="\033[1m"

# ── KANGAROO BIN ──────────────────────────────────────────
BIN = "kangaroo.exe" if IS_WIN else "kangaroo"
CARGO_BIN = os.path.expanduser(f"~/.cargo/bin/{BIN}")

def banner():
    os.system("cls" if IS_WIN else "clear")
    gpu_info = "Vulkan/DX12 (Windows)" if IS_WIN else \
               "Metal (Apple Silicon)" if IS_MAC else \
               "Vulkan (Linux)"
    print(f"\n{M}{'='*62}{R}")
    print(f"{BD}  ⛏  PUZZLE135  Universal Worker  v{VERSION}{R}")
    print(f"{M}{'─'*62}{R}")
    print(f"{C}  WAX    : {BD}{W}{WAX_ACCOUNT}{R}")
    print(f"{C}  Pool   : {W}{POOL_URL}{R}")
    print(f"{C}  Sistem : {W}{SYS} {ARCH}{R}")
    print(f"{C}  GPU    : {M}{gpu_info} — otomatik algılanır{R}")
    print(f"{M}{'─'*62}{R}")
    print(f"{G}  Her {NFT_THRESHOLD:,} Bkeys = 1 NFT  →  {WAX_ACCOUNT}{R}")
    print(f"{M}{'='*62}{R}\n")

# ── KANGAROO BUL ──────────────────────────────────────────
def find_kangaroo():
    # 1. Mevcut klasörde
    local = f".\\{BIN}" if IS_WIN else f"./{BIN}"
    if os.path.exists(BIN):
        return local
    # 2. cargo bin
    if os.path.exists(CARGO_BIN):
        return CARGO_BIN
    # 3. PATH'te
    try:
        r = subprocess.run([BIN, "--version"], capture_output=True, timeout=5)
        if r.returncode == 0:
            return BIN
    except: pass
    return None

# ── KANGAROO KUR ──────────────────────────────────────────
def install_kangaroo():
    print(f"\n{Y}[i] Kangaroo bulunamadı. Otomatik kuruluyor...{R}")
    print(f"{Y}    Bu işlem 5-10 dakika sürer, bir kez yapılır.{R}\n")

    cargo_dir = os.path.expanduser("~/.cargo/bin")
    cargo_exe = os.path.join(cargo_dir, "cargo.exe" if IS_WIN else "cargo")
    rustup_exe = os.path.join(cargo_dir, "rustup.exe" if IS_WIN else "rustup")

    # 1. Rust var mı?
    if not os.path.exists(cargo_exe):
        print(f"{Y}[1/3] Rust indiriliyor...{R}")
        try:
            if IS_WIN:
                url = "https://static.rust-lang.org/rustup/dist/x86_64-pc-windows-msvc/rustup-init.exe"
                tmp = os.path.join(os.environ.get("TEMP", "."), "rustup-init.exe")
                urllib.request.urlretrieve(url, tmp)
                print(f"{Y}[1/3] Rust kuruluyor...{R}")
                subprocess.run([tmp, "-y", "--default-toolchain", "stable",
                               "--profile", "minimal"], check=True)
                os.remove(tmp)
            else:
                subprocess.run(
                    'curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal',
                    shell=True, check=True
                )
            os.environ["PATH"] = cargo_dir + os.pathsep + os.environ.get("PATH", "")
            print(f"{G}[✓] Rust kuruldu.{R}")
        except Exception as e:
            print(f"{RE}[✗] Rust kurulamadı: {e}{R}")
            return False
    else:
        print(f"{G}[✓] Rust mevcut.{R}")

    # PATH güncelle
    os.environ["PATH"] = cargo_dir + os.pathsep + os.environ.get("PATH", "")

    # 2. Default toolchain
    try:
        subprocess.run([rustup_exe, "default", "stable"], check=True,
                      capture_output=True)
    except: pass

    # 3. Kangaroo kur
    print(f"\n{Y}[2/3] Kangaroo GPU kuruluyor (cargo install kangaroo)...{R}")
    try:
        subprocess.run([cargo_exe, "install", "kangaroo"], check=True)
        print(f"\n{G}[✓] Kangaroo GPU kuruldu!{R}")
        return True
    except Exception as e:
        print(f"{RE}[✗] Kangaroo kurulamadı: {e}{R}")
        return False

# ── POOL REPORTER ─────────────────────────────────────────
_lock=threading.Lock()
_pending=0; _total=0; _speed=0.0; _nfts=0; _start=time.time()
_last_ops=0; _last_ops_time=time.time()

def reporter():
    global _pending, _nfts
    while True:
        time.sleep(REPORT_SECS)
        with _lock:
            bk=_pending; _pending=0
        if bk<=0: continue
        try:
            data=json.dumps({
                "wax_account": WAX_ACCOUNT,
                "bkeys"      : bk,
                "gpu_type"   : "gpu",
                "speed_mkeys": round(_speed, 2),
                "version"    : VERSION
            }).encode()
            req=urllib.request.Request(
                f"{POOL_URL}/api/report", data=data, method="POST",
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                resp=json.loads(r.read())
            _nfts  = resp.get("user_total_nfts", _nfts)
            new    = resp.get("new_nfts_minted", 0)
            until  = resp.get("bkeys_until_next_nft", NFT_THRESHOLD)
            msg = f"\n{G}[✓] {bk:,} Bkeys gönderildi | NFT: {_nfts}"
            if new > 0:
                msg += f" | {BD}+{new} NFT MINT! 🎉{R}{G}"
            msg += f" | Sonraki: {until:,} Bkeys{R}"
            print(msg)
        except Exception as e:
            print(f"\n{Y}[!] Rapor gönderilemedi: {e}{R}")

def son_rapor():
    with _lock:
        bk = _pending
    if bk <= 0: return
    try:
        data = json.dumps({"wax_account":WAX_ACCOUNT,"bkeys":bk,
            "gpu_type":"gpu","speed_mkeys":round(_speed,2)}).encode()
        req = urllib.request.Request(f"{POOL_URL}/api/report", data=data,
            method="POST", headers={"Content-Type":"application/json"})
        urllib.request.urlopen(req, timeout=8)
    except: pass

atexit.register(son_rapor)
try:
    signal.signal(signal.SIGTERM, lambda s,f: sys.exit(0))
    signal.signal(signal.SIGINT,  lambda s,f: sys.exit(0))
except: pass

# ── STATUS ────────────────────────────────────────────────
def time_per_nft(s):
    if s <= 0: return "—"
    sec = (NFT_THRESHOLD * 1000) / s
    if sec < 60:    return f"{int(sec)}s"
    if sec < 3600:  return f"{sec/60:.1f}m"
    if sec < 86400: return f"{sec/3600:.1f}h"
    return f"{sec/86400:.1f}g"

def nfts_per_day(s):
    return (s * 86400) / (NFT_THRESHOLD * 1000) if s > 0 else 0

def status(spd, bkt, nfts, elapsed):
    bar   = "█"*min(20,int(spd/10)) + "░"*(20-min(20,int(spd/10)))
    h = int(elapsed)//3600; m=(int(elapsed)%3600)//60; s=int(elapsed)%60
    bk    = f"{bkt/1e6:.1f}M" if bkt>=1e6 else f"{bkt//1000}K"
    npd   = nfts_per_day(spd)
    nxt   = time_per_nft(spd)
    rate  = f"{npd:.1f}/gun" if npd >= 1 else f"1/{nxt}"
    sys.stdout.write(
        f"\r{M}[⚡]{R} {spd:6.1f} Mops/s {C}[{bar}]{R} "
        f"NFT:{G}{nfts}{R}({Y}{rate}{R}) "
        f"Next:{G}{nxt}{R} "
        f"Bkeys:{W}{bk}{R} "
        f"{Y}{h:02d}:{m:02d}:{s:02d}{R}   "
    )
    sys.stdout.flush()

# ── ÇÖZÜLDÜ ───────────────────────────────────────────────
def cozuldu(line):
    print(f"\n\n{G}{'★'*60}{R}")
    print(f"{BD}{G}  🎉 PUZZLE #135 ÇÖZÜLDÜ! 🎉{R}")
    print(f"{G}  {line}{R}")
    print(f"{G}{'★'*60}{R}\n")
    try:
        data = json.dumps({"wax_account":WAX_ACCOUNT,"line":line,"gpu_type":"gpu"}).encode()
        req  = urllib.request.Request(f"{POOL_URL}/api/solved", data=data,
               method="POST", headers={"Content-Type":"application/json"})
        urllib.request.urlopen(req, timeout=10)
        print(f"{G}[✓] Pool'a bildirildi!{R}")
    except: pass
    input(f"\n{Y}Enter'a bas...{R}")

# ── KANGAROO ÇALIŞTIR ─────────────────────────────────────
def run(kangaroo_bin):
    global _pending, _total, _speed, _last_ops, _last_ops_time

    cmd = [
        kangaroo_bin,
        "--pubkey", PUBKEY,
        "--start",  RANGE_START,
        "--range",  RANGE_BITS,
    ]
    print(f"{C}[►] {' '.join(cmd)}{R}\n")

    log_f = open("kangaroo_log.txt", "w", buffering=1)
    try:
        proc = subprocess.Popen(cmd, stdout=log_f, stderr=log_f)
    except Exception as e:
        print(f"{RE}[✗] Başlatılamadı: {e}{R}")
        log_f.close(); return

    print(f"{G}[✓] GPU taraması başladı — kangaroo_log.txt{R}\n")
    time.sleep(3)

    last_pos = 0
    while True:
        time.sleep(0.5)
        try:
            with open("kangaroo_log.txt", "r", errors="replace") as lf:
                lf.seek(last_pos)
                data = lf.read()
                last_pos = lf.tell()
        except: data = ""

        for line in data.replace("\r", "\n").split("\n"):
            line = line.strip()
            if not line: continue

            # Hız: "Ops: 83M" formatı
            m = re.search(r'Ops:\s*([\d.]+)([MBGKk]?)', line, re.I)
            if m:
                val  = float(m.group(1))
                unit = m.group(2).upper()
                if unit == '':  val /= 1_000_000
                elif unit=='K': val /= 1000
                elif unit=='B': val *= 1000
                elif unit=='G': val *= 1_000_000
                # Hız = ops farkı / zaman farkı
                now = time.time()
                dt  = now - _last_ops_time
                if dt > 0 and _last_ops > 0:
                    _speed = (val - _last_ops) / dt if val > _last_ops else val / 14
                else:
                    _speed = val / 14
                _last_ops      = val
                _last_ops_time = now
                bk = max(1, int(_speed * 14 * 0.3))
                with _lock:
                    _pending += bk
                    _total   += bk
                status(_speed, _total, _nfts, time.time()-_start)
                continue

            # Çözüm — sadece hex key içeren satır
            if re.search(r'(?:found|key)[^\n]{0,30}0x[0-9a-f]{40,}', line, re.I):
                cozuldu(line); continue

            # GPU bilgi satırları
            ll = line.lower()
            if any(k in ll for k in ["gpu:","vulkan","dx12","metal","error",
                                      "backend","calibrat","shader","pipeline",
                                      "using"]):
                print(f"\n{Y}[i] {line}{R}")

        if proc.poll() is not None:
            log_f.close()
            rc = proc.returncode
            if rc != 0:
                print(f"\n{RE}[!] Kangaroo hata ile bitti (kod:{rc}).{R}")
                try:
                    with open("kangaroo_log.txt") as lf:
                        lines = [l.strip() for l in lf.readlines() if l.strip()]
                        for l in lines[-5:]:
                            print(f"  {Y}{l}{R}")
                except: pass
            else:
                print(f"\n{G}[✓] Kangaroo tamamlandı.{R}")
            break

# ── ANA PROGRAM ───────────────────────────────────────────
def check_pool():
    try:
        with urllib.request.urlopen(f"{POOL_URL}/api/stats", timeout=10) as r:
            d = json.loads(r.read())
            print(f"{G}[✓] Pool OK | NFT: {d.get('total_nfts',0)} | Worker: {d.get('active_workers',0)}{R}")
    except Exception as e:
        print(f"{Y}[!] Pool bağlantısı yok: {e} — Offline mod.{R}")

def main():
    banner()
    check_pool()
    print()

    # Kangaroo bul veya kur
    kangaroo_bin = find_kangaroo()
    if not kangaroo_bin:
        success = install_kangaroo()
        if success:
            kangaroo_bin = find_kangaroo()
        if not kangaroo_bin:
            print(f"\n{RE}[✗] Kangaroo bulunamadı.{R}")
            print(f"{Y}    Manuel kur: cargo install kangaroo{R}")
            input(f"\n{Y}Enter'a bas...{R}")
            sys.exit(1)

    print(f"{G}[✓] Kangaroo: {kangaroo_bin}{R}\n")

    threading.Thread(target=reporter, daemon=True).start()
    print(f"{G}[✓] Reporter başlatıldı (her {REPORT_SECS}s).{R}\n")
    print(f"{M}{'─'*62}{R}")
    print(f"{BD}  GPU taraması başlıyor... Durdurmak için CTRL+C{R}")
    print(f"{M}{'─'*62}{R}\n")

    try:
        run(kangaroo_bin)
    except KeyboardInterrupt:
        e = time.time()-_start
        h = int(e)//3600; m=(int(e)%3600)//60
        print(f"\n\n{Y}Durduruldu. Süre:{h:02d}:{m:02d} | Bkeys:{_total:,} | NFT:{_nfts}{R}")

    input(f"\n{Y}Çıkmak için Enter...{R}")

if __name__ == "__main__":
    main()
