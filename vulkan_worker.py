#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PUZZLE135 — Vulkan Worker v2.0
Bitcoin Puzzle #135 Pool Client
AMD / Intel GPU — CUDA gerekmez
"""

import os, sys, time, json, threading, subprocess, platform
import urllib.request, urllib.error, re, io

# ── CONFIG (sunucu tarafından inject edilir) ───────────────
WAX_ACCOUNT     = "__WAX_ACCOUNT__"
POOL_URL        = "__POOL_URL__"
GPU_TYPE        = "vulkan"
VERSION         = "2.0.0"
PUBKEY          = "02145d2611c823a396ef6712ce0f712f09b9b4f3135e3e0aa3230fb9b6d08d1e16"
RANGE_START     = "4000000000000000000000000000000000"
RANGE_END       = "7fffffffffffffffffffffffffffffffff"
REPORT_SECS     = 30
NFT_THRESHOLD   = 10000

# ── RENKLER ───────────────────────────────────────────────
IS_WIN = platform.system() == "Windows"
if IS_WIN:
    os.system("color")

R  = "\033[0m"
G  = "\033[92m"
Y  = "\033[93m"
RE = "\033[91m"
C  = "\033[96m"
M  = "\033[95m"
W  = "\033[97m"
BD = "\033[1m"

# ── KANGAROO ──────────────────────────────────────────────
BIN = "kangaroo.exe" if IS_WIN else "kangaroo"

DOWNLOAD_URLS = {
    "Windows": "https://github.com/JeanLucPons/Kangaroo/releases/download/1.0/Kangaroo.exe",
    "Linux"  : "https://github.com/JeanLucPons/Kangaroo/releases/download/1.0/kangaroo",
}

def banner():
    os.system("cls" if IS_WIN else "clear")
    print(f"""
{M}{'='*62}{R}
{BD}  PUZZLE135  Vulkan Worker  v{VERSION}{R}
{M}{'─'*62}{R}
{C}  WAX  : {BD}{W}{WAX_ACCOUNT}{R}
{C}  Pool : {W}{POOL_URL}{R}
{C}  GPU  : {M}AMD / Intel Vulkan{R}
{M}{'─'*62}{R}
{G}  Her {NFT_THRESHOLD:,} Bkeys = 1 NFT  →  ibdak.c.wam'a mint edilir{R}
{M}{'='*62}{R}
""")

# ── KANGaROO İNDİR ────────────────────────────────────────
def download_kangaroo():
    if os.path.exists(BIN):
        print(f"{G}[✓] Kangaroo mevcut: {BIN}{R}")
        return True
    url = DOWNLOAD_URLS.get(platform.system())
    if not url:
        print(f"{RE}[✗] Bu OS desteklenmiyor.{R}")
        return False
    print(f"{Y}[↓] Kangaroo indiriliyor...{R}")
    try:
        done = [False]
        def prog(b, bs, total):
            if total > 0 and not done[0]:
                pct = min(100, b*bs*100//total)
                bar = "█"*(pct//4) + "░"*(25-pct//4)
                sys.stdout.write(f"\r    [{bar}] {pct}%  ")
                sys.stdout.flush()
                if pct >= 100: done[0] = True
        urllib.request.urlretrieve(url, BIN, reporthook=prog)
        print(f"\n{G}[✓] İndirildi: {BIN}{R}")
        if not IS_WIN:
            os.chmod(BIN, 0o755)
        return True
    except Exception as e:
        print(f"\n{RE}[✗] İndirme hatası: {e}{R}")
        print(f"{Y}    Manuel indir: {url}{R}")
        return False

# ── POOL REPORTER ─────────────────────────────────────────
_lock          = threading.Lock()
_bkeys_pending = 0
_total_bkeys   = 0
_speed         = 0.0
_nfts          = 0
_start         = time.time()

def reporter():
    global _bkeys_pending, _nfts
    while True:
        time.sleep(REPORT_SECS)
        with _lock:
            bk = _bkeys_pending
            _bkeys_pending = 0
        if bk <= 0:
            continue
        try:
            data = json.dumps({
                "wax_account" : WAX_ACCOUNT,
                "bkeys"       : bk,
                "gpu_type"    : GPU_TYPE,
                "speed_mkeys" : round(_speed, 2),
                "version"     : VERSION
            }).encode()
            req = urllib.request.Request(
                f"{POOL_URL}/api/report",
                data=data, method="POST",
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                resp = json.loads(r.read())
            _nfts    = resp.get("user_total_nfts", _nfts)
            new_nfts = resp.get("new_nfts_minted", 0)
            until    = resp.get("bkeys_until_next_nft", NFT_THRESHOLD)
            msg = f"\n{G}[✓] Rapor gönderildi → {bk:,} Bkeys"
            if new_nfts > 0:
                msg += f" | {G}{BD}+{new_nfts} NFT MINT!{R}"
            msg += f" | Toplam NFT: {_nfts} | Sonraki: {until:,} Bkeys{R}"
            print(msg)
        except Exception as e:
            print(f"\n{Y}[!] Rapor gönderilemedi: {e}{R}")

# ── HIZLANDIRILMIŞ ÇIKTI OKUMA ────────────────────────────
def time_per_nft(speed):
    if speed <= 0: return "—"
    secs = (NFT_THRESHOLD * 1000) / speed
    if secs < 60:   return f"{int(secs)}s"
    if secs < 3600: return f"{secs/60:.1f}m"
    return f"{secs/3600:.1f}h"

def nfts_per_day(speed):
    if speed <= 0: return 0
    return (speed * 86400) / (NFT_THRESHOLD * 1000)

def status(speed, bk_total, nfts, elapsed):
    bar_w  = 24
    filled = min(bar_w, int(speed / 50))
    bar    = "█"*filled + "░"*(bar_w-filled)
    h      = int(elapsed)//3600
    m      = (int(elapsed)%3600)//60
    s      = int(elapsed)%60
    bk_str = f"{bk_total/1e6:.1f}M" if bk_total >= 1e6 else f"{bk_total//1000}K"
    npd    = nfts_per_day(speed)
    nxt    = time_per_nft(speed)
    rate   = f"{npd:.1f}/day" if npd >= 1 else f"1/{nxt}"
    sys.stdout.write(
        f"\r{M}[⚡]{R} {speed:6.1f} Mkeys/s "
        f"{C}[{bar}]{R} "
        f"NFT:{G}{nfts}{R}({Y}{rate}{R}) "
        f"Next:{G}{nxt}{R} "
        f"Bkeys:{W}{bk_str}{R} "
        f"{Y}{h:02d}:{m:02d}:{s:02d}{R}   "
    )
    sys.stdout.flush()

# ── KANGAROO ÇALIŞTIR ─────────────────────────────────────
def run_kangaroo():
    global _bkeys_pending, _total_bkeys, _speed

    # Puzzle dosyası — JeanLucPons formatı
    with open("puzzle135.txt", "w") as f:
        f.write(f"{RANGE_START}\n{RANGE_END}\n{PUBKEY}\n")
    print(f"{G}[✓] puzzle135.txt oluşturuldu.{R}")

    cmd = ([BIN] if IS_WIN else [f"./{BIN}"]) + ["puzzle135.txt"]
    print(f"\n{C}[►] Başlatılıyor: {' '.join(cmd)}{R}")
    print(f"{Y}    Kangaroo ayrı pencerede açılıyor...{R}\n")

    try:
        if IS_WIN:
            # Windows: yeni CMD penceresinde aç — çıktı görünür
            proc = subprocess.Popen(
                ["cmd", "/c", "start", "cmd", "/k"] + cmd,
                close_fds=True
            )
        else:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT
            )
    except FileNotFoundError:
        print(f"{RE}[✗] {BIN} bulunamadı!{R}")
        return

    if IS_WIN:
        # Windows'ta Kangaroo ayrı pencerede — biz sadece hızı tahmin ederiz
        print(f"{G}[✓] Kangaroo başlatıldı — yeni pencerede çalışıyor.{R}")
        print(f"{G}[✓] Bu pencere pool raporlarını göndermeye devam ediyor.{R}\n")

        # Hız tahmini: integrated GPU için ~20 Mkeys/s
        ESTIMATED_SPEED = 20.0
        print(f"{Y}[i] Tahmini hız: {ESTIMATED_SPEED} Mkeys/s (integrated GPU){R}")
        print(f"{Y}[i] Her 30 saniyede pool'a rapor gönderilecek.{R}\n")

        while True:
            time.sleep(1)
            with _lock:
                _bkeys_pending += int(ESTIMATED_SPEED * 1)
                _total_bkeys   += int(ESTIMATED_SPEED * 1)
            _speed = ESTIMATED_SPEED
            elapsed = time.time() - _start
            status(ESTIMATED_SPEED, _total_bkeys, _nfts, elapsed)

            # Kangaroo kapandıysa dur
            if proc.poll() is not None:
                print(f"\n{Y}[!] Kangaroo sona erdi.{R}")
                break
    else:
        # Linux: normal pipe okuma
        buf = b""
        while True:
            ch = proc.stdout.read(1)
            if not ch:
                break
            if ch in (b'\r', b'\n'):
                if not buf:
                    continue
                try:
                    line = buf.decode('utf-8', errors='replace').strip()
                except:
                    line = ""
                buf = b""
                if not line:
                    continue
                m = re.search(r'\[([\d.]+)\s*([MBGKk])Key/s\]', line, re.I)
                if m:
                    val = float(m.group(1))
                    unit = m.group(2).upper()
                    if unit == 'K': val /= 1000
                    elif unit == 'B': val *= 1000
                    elif unit == 'G': val *= 1_000_000
                    _speed = val
                    bk = int(val * 1)
                    with _lock:
                        _bkeys_pending += bk
                        _total_bkeys   += bk
                    status(val, _total_bkeys, _nfts, time.time()-_start)
                    continue
                ll = line.lower()
                if any(k in ll for k in ["priv", "pkey", "key found", "solved"]):
                    solved(line)
                if any(k in ll for k in ["start:", "stop:", "error", "dp size"]):
                    print(f"\n{Y}[i] {line}{R}")
            else:
                buf += ch
        proc.wait()
        print(f"\n{Y}[!] Kangaroo sona erdi (kod: {proc.returncode}).{R}")

def solved(line):
    print(f"\n\n{G}{'★'*60}{R}")
    print(f"{BD}{G}  🎉 PUZZLE #135 ÇÖZÜLDÜ! 🎉{R}")
    print(f"{G}  {line}{R}")
    print(f"{G}{'★'*60}{R}\n")
    try:
        data = json.dumps({"wax_account":WAX_ACCOUNT,"line":line,"gpu_type":GPU_TYPE}).encode()
        req  = urllib.request.Request(f"{POOL_URL}/api/solved", data=data,
               method="POST", headers={"Content-Type":"application/json"})
        urllib.request.urlopen(req, timeout=10)
        print(f"{G}[✓] Pool'a bildirildi!{R}")
    except Exception as e:
        print(f"{RE}[!] Bildirim gönderilemedi: {e}{R}")
        print(f"{Y}    Private key'i sakla: {line}{R}")
    input(f"\n{Y}Enter'a bas...{R}")

# ── GPU KONTROL ────────────────────────────────────────────
def check_gpu():
    print(f"{C}[i] GPU kontrol ediliyor...{R}")
    try:
        r = subprocess.run(["vulkaninfo","--summary"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            for ln in r.stdout.split('\n'):
                if 'deviceName' in ln or 'deviceType' in ln:
                    print(f"{G}[✓] Vulkan GPU: {ln.strip()}{R}")
                    break
        else:
            print(f"{Y}[!] vulkaninfo bulunamadı, devam ediliyor...{R}")
    except:
        print(f"{Y}[!] GPU doğrulama atlandı.{R}")

# ── POOL KONTROL ───────────────────────────────────────────
def check_pool():
    print(f"{C}[i] Pool kontrol ediliyor: {POOL_URL}{R}")
    try:
        with urllib.request.urlopen(f"{POOL_URL}/api/stats", timeout=10) as r:
            d = json.loads(r.read())
            print(f"{G}[✓] Pool OK  |  NFT: {d.get('total_nfts',0)}  |  Worker: {d.get('active_workers',0)}{R}")
            return True
    except Exception as e:
        print(f"{Y}[!] Pool bağlantısı kurulamadı: {e}{R}")
        print(f"{Y}    Offline modda devam ediliyor.{R}")
        return False

# ── ANA PROGRAM ────────────────────────────────────────────
def main():
    banner()
    check_gpu()
    print()
    check_pool()
    print()

    if not download_kangaroo():
        input(f"\n{RE}Çıkmak için Enter...{R}")
        sys.exit(1)
    print()

    t = threading.Thread(target=reporter, daemon=True)
    t.start()
    print(f"{G}[✓] Pool reporter başlatıldı (her {REPORT_SECS}s'de rapor).{R}")
    print(f"{G}[✓] NFT'ler mint edilecek: {BD}{WAX_ACCOUNT}{R}")
    print()
    print(f"{M}{'─'*62}{R}")
    print(f"{BD}  Tarama başlıyor... Durdurmak için CTRL+C{R}")
    print(f"{M}{'─'*62}{R}\n")

    try:
        run_kangaroo()
    except KeyboardInterrupt:
        elapsed = time.time() - _start
        h = int(elapsed)//3600
        m = (int(elapsed)%3600)//60
        print(f"\n\n{Y}[!] Durduruldu.{R}")
        print(f"{C}  Süre   : {h:02d}:{m:02d}{R}")
        print(f"{C}  Bkeys  : {_total_bkeys:,}{R}")
        print(f"{C}  NFT    : {_nfts}{R}")

    input(f"\n{Y}Çıkmak için Enter...{R}")

if __name__ == "__main__":
    main()
