#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════╗
║         PUZZLE135 — CUDA Worker  v1.0                   ║
║   Bitcoin Puzzle #135 Distributed Mining Pool           ║
║   WAX Koleksiyon: puzzle135btc  |  AtomicHub            ║
╚══════════════════════════════════════════════════════════╝
Bu dosya sunucu tarafından WAX hesabınıza özel üretilmiştir.
Çift tıklayarak çalıştırın — başka bir şey gerekmez!
"""

import os, sys, time, json, threading, subprocess, platform
import urllib.request, urllib.error, re, hashlib, struct

# ═══════════════════════════════════════════════════════════
#  CONFIG  (sunucu tarafından inject edilir)
# ═══════════════════════════════════════════════════════════
WAX_ACCOUNT     = "__WAX_ACCOUNT__"
POOL_URL        = "__POOL_URL__"
GPU_TYPE        = "cuda"
VERSION         = "1.0.0"

# Puzzle 135 sabit parametreler
PUBKEY          = "02145d2611c823a396ef6712ce0f712f09b9b4f3135e3e0aa3230fb9b6d08d1e16"
RANGE_START     = "4000000000000000000000000000000000"
RANGE_END       = "7fffffffffffffffffffffffffffffffff"
PUZZLE_FILE     = "puzzle135.txt"
REPORT_SECS     = 30      # Pool'a kaç saniyede bir rapor gönder

# ═══════════════════════════════════════════════════════════
#  RENK KODLARI
# ═══════════════════════════════════════════════════════════
IS_WIN = platform.system() == "Windows"
if IS_WIN:
    os.system("color")

R  = "\033[0m"
G  = "\033[92m"
Y  = "\033[93m"
RE = "\033[91m"
C  = "\033[96m"
B  = "\033[94m"
M  = "\033[95m"
W  = "\033[97m"
BD = "\033[1m"

def cls():
    os.system("cls" if IS_WIN else "clear")

def banner():
    cls()
    w = 62
    print(f"\n{Y}{'═'*w}{R}")
    print(f"{BD}{Y}  ⛏  PUZZLE135  ·  NVIDIA CUDA Worker  ·  v{VERSION}{R}")
    print(f"{Y}{'─'*w}{R}")
    print(f"{C}  WAX  : {BD}{W}{WAX_ACCOUNT}{R}")
    print(f"{C}  Pool : {W}{POOL_URL}{R}")
    print(f"{C}  GPU  : {G}NVIDIA CUDA{R}")
    print(f"{C}  NFT  : {W}puzzle135btc (AtomicHub){R}")
    print(f"{Y}{'─'*w}{R}")
    print(f"{G}  ✦  Her 100 Bkeys katkında 1 NFT otomatik mint edilir{R}")
    print(f"{Y}{'═'*w}{R}\n")

# ═══════════════════════════════════════════════════════════
#  KANGAROO (CUDA) İNDİR
# ═══════════════════════════════════════════════════════════
KANGAROO_URLS = {
    "Windows": {
        "url"  : "https://github.com/JeanLucPons/Kangaroo/releases/latest/download/Kangaroo.exe",
        "bin"  : "Kangaroo.exe",
    },
    "Linux": {
        "url"  : "https://github.com/JeanLucPons/Kangaroo/releases/latest/download/kangaroo",
        "bin"  : "kangaroo",
    },
}

def get_kangaroo_info():
    info = KANGAROO_URLS.get(platform.system(), KANGAROO_URLS["Linux"])
    return info["url"], info["bin"]

def download_file(url, dest, label="Dosya"):
    print(f"{Y}[↓] {label} indiriliyor...{R}")
    try:
        done = [False]
        def progress(block, block_size, total):
            if total > 0 and not done[0]:
                pct = min(100, block * block_size * 100 // total)
                bar = "█" * (pct // 4) + "░" * (25 - pct // 4)
                sys.stdout.write(f"\r    [{bar}] {pct}%  ")
                sys.stdout.flush()
                if pct >= 100:
                    done[0] = True
        urllib.request.urlretrieve(url, dest, reporthook=progress)
        print(f"\n{G}[✓] {label} indirildi → {dest}{R}")
        return True
    except Exception as e:
        print(f"\n{RE}[✗] İndirme hatası: {e}{R}")
        return False

def ensure_kangaroo():
    url, bin_name = get_kangaroo_info()
    if os.path.exists(bin_name):
        print(f"{G}[✓] Kangaroo (CUDA) zaten mevcut: {bin_name}{R}")
        return bin_name
    if not download_file(url, bin_name, "Kangaroo CUDA"):
        return None
    if not IS_WIN:
        os.chmod(bin_name, 0o755)
    return bin_name

def write_puzzle_file():
    content = f"{RANGE_START}\n{RANGE_END}\n{PUBKEY}\n"
    with open(PUZZLE_FILE, "w") as f:
        f.write(content)
    print(f"{G}[✓] {PUZZLE_FILE} oluşturuldu.{R}")

# ═══════════════════════════════════════════════════════════
#  POOL REPORTER  (arka planda)
# ═══════════════════════════════════════════════════════════
_lock            = threading.Lock()
_bkeys_pending   = 0
_total_bkeys     = 0
_current_speed   = 0.0
_nfts_earned     = 0
_session_start   = time.time()

def _send(endpoint, payload):
    try:
        data = json.dumps(payload).encode()
        req  = urllib.request.Request(
            f"{POOL_URL}{endpoint}",
            data    = data,
            headers = {"Content-Type": "application/json"},
            method  = "POST"
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        raise e

def reporter_thread():
    global _bkeys_pending, _nfts_earned
    while True:
        time.sleep(REPORT_SECS)
        with _lock:
            bk = _bkeys_pending
            _bkeys_pending = 0
        if bk <= 0:
            continue
        try:
            resp = _send("/api/report", {
                "wax_account" : WAX_ACCOUNT,
                "bkeys"       : bk,
                "gpu_type"    : GPU_TYPE,
                "speed_mkeys" : round(_current_speed, 2),
                "version"     : VERSION
            })
            _nfts_earned = resp.get("user_nfts", _nfts_earned)
            total_pool   = resp.get("total_nfts", 0)
            new_nfts     = resp.get("new_nfts", 0)
            nft_str      = f"  {G}+{new_nfts} NFT MINT!{R}" if new_nfts > 0 else ""
            print(f"\n{G}[✓] Pool raporu → {bk:,} Bkeys | "
                  f"NFT'lerim: {_nfts_earned} | "
                  f"Toplam Havuz NFT: {total_pool}{nft_str}{R}")
        except Exception as e:
            print(f"\n{Y}[!] Rapor gönderilemedi: {e}{R}")

# ═══════════════════════════════════════════════════════════
#  KANGAROO ÇALIŞTIRICISI
# ═══════════════════════════════════════════════════════════
_speed_pattern = re.compile(
    r'(\d+\.?\d*)\s*([MBGKk])\s*(?:key|Key)s?/s', re.IGNORECASE
)
_solved_keywords = [
    "priv", "private key", "key#", "found", "solved", "winner"
]

def parse_speed(line):
    """Satırdan hız değerini Mkeys/s cinsinden çıkar"""
    m = _speed_pattern.search(line)
    if not m:
        return None
    val, unit = float(m.group(1)), m.group(2).upper()
    if unit == 'K': val /= 1000
    elif unit == 'B': val *= 1000
    elif unit == 'G': val *= 1_000_000
    return val


def time_to_next_nft(speed_mkeys, bkeys_total, nfts_minted):
    """Bir sonraki NFT için kalan süre"""
    if speed_mkeys <= 0: return "—"
    remaining_bkeys = REPORT_INTERVAL - (bkeys_total % REPORT_INTERVAL)
    if remaining_bkeys <= 0: remaining_bkeys = REPORT_INTERVAL
    secs = (remaining_bkeys * 1000) / speed_mkeys
    if secs < 60:   return f"{int(secs)}s"
    if secs < 3600: return f"{secs/60:.1f}m"
    return f"{secs/3600:.1f}h"

def nfts_per_day(speed_mkeys):
    """Günde tahmini NFT sayısı"""
    if speed_mkeys <= 0: return 0
    return (speed_mkeys * 86400) / (100 * 1000)

def status_bar(speed, bkeys_total, nfts, elapsed):
    """Tek satırlık durum çubuğu + NFT zamanlayıcı"""
    bar_len  = 26
    filled   = min(bar_len, int(speed / 100))
    bar      = "█" * filled + "░" * (bar_len - filled)
    hrs      = int(elapsed) // 3600
    mins     = (int(elapsed) % 3600) // 60
    secs     = int(elapsed) % 60
    bk_str   = f"{bkeys_total/1e6:.1f}M" if bkeys_total >= 1e6 else f"{bkeys_total//1000}K"
    npd      = nfts_per_day(speed)
    nxt      = time_to_next_nft(speed, bkeys_total, nfts)
    npd_str  = f"{npd:.1f}/day" if npd >= 1 else f"1/{nxt}"
    sys.stdout.write(
        f"\r{G}[⚡]{R} {speed:6.1f} Mkeys/s  "
        f"{C}[{bar}]{R}  "
        f"NFT:{G}{nfts}{R}({Y}{npd_str}{R})  "
        f"Next:{G}{nxt}{R}  "
        f"Bkeys:{W}{bk_str}{R}  "
        f"{Y}{hrs:02d}:{mins:02d}:{secs:02d}{R}   "
    )
    sys.stdout.flush()

def run_kangaroo(bin_name):
    global _bkeys_pending, _total_bkeys, _current_speed

    cmd = [f"./{bin_name}", "-gpu", PUZZLE_FILE]
    if IS_WIN:
        cmd = [bin_name, "-gpu", PUZZLE_FILE]

    print(f"{C}[►] Kangaroo başlatılıyor: {' '.join(cmd)}{R}\n")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout = subprocess.PIPE,
            stderr = subprocess.STDOUT,
            text   = True,
            bufsize= 1,
        )
    except FileNotFoundError:
        print(f"{RE}[✗] '{bin_name}' bulunamadı!{R}")
        print(f"{Y}    CUDA sürücüsü yüklü mü? (nvidia-smi komutunu deneyin){R}")
        return

    for raw_line in proc.stdout:
        line = raw_line.strip()
        if not line:
            continue

        # ─ Hız tespiti ─────────────────────────────────
        speed = parse_speed(line)
        if speed is not None:
            _current_speed = speed
            bk_delta       = int(speed * 1)   # 1 saniyelik tahmin
            with _lock:
                _bkeys_pending += bk_delta
                _total_bkeys   += bk_delta
            elapsed = time.time() - _session_start
            status_bar(speed, _total_bkeys, _nfts_earned, elapsed)
            continue

        # ─ Çözüm tespiti ────────────────────────────────
        ll = line.lower()
        if any(k in ll for k in _solved_keywords):
            _handle_solved(line)
            continue

        # ─ Diğer önemli satırlar ─────────────────────
        if any(k in ll for k in ["error", "cuda", "device", "gpu", "warning", "init"]):
            print(f"\n{Y}[i] {line}{R}")

    proc.wait()
    print(f"\n{Y}[!] Kangaroo süreci sona erdi (kod: {proc.returncode}).{R}")

def _handle_solved(line):
    """Puzzle çözüldüğünde çağrılır"""
    print(f"\n\n{G}{'★'*64}{R}")
    print(f"{BD}{G}     🎉  PUZZLE #135 ÇÖZÜLDÜ!  🎉{R}")
    print(f"{G}     {line}{R}")
    print(f"{G}{'★'*64}{R}\n")
    try:
        _send("/api/solved", {
            "wax_account": WAX_ACCOUNT,
            "line"       : line,
            "gpu_type"   : GPU_TYPE
        })
        print(f"{G}[✓] Çözüm pool sunucusuna bildirildi!{R}")
    except Exception as e:
        print(f"{RE}[!] Sunucuya bildirim gönderilemedi: {e}{R}")
        print(f"{Y}    Lütfen bu private key'i sakla: {line}{R}")
    input(f"\n{Y}Devam etmek için Enter'a basın...{R}")

# ═══════════════════════════════════════════════════════════
#  NVIDIA GPU KONTROLÜ
# ═══════════════════════════════════════════════════════════
def check_nvidia():
    print(f"{C}[i] NVIDIA GPU kontrol ediliyor...{R}")
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=8
        )
        if r.returncode == 0:
            for ln in r.stdout.strip().split('\n'):
                print(f"{G}[✓] GPU: {ln.strip()}{R}")
            return True
        else:
            print(f"{RE}[!] nvidia-smi hata verdi.{R}")
    except FileNotFoundError:
        print(f"{Y}[!] nvidia-smi bulunamadı. NVIDIA sürücüsü yüklü mü?{R}")
    except Exception as e:
        print(f"{Y}[!] GPU kontrol hatası: {e}{R}")
    return False

# ═══════════════════════════════════════════════════════════
#  POOL BAĞLANTI TESTİ
# ═══════════════════════════════════════════════════════════
def check_pool():
    print(f"{C}[i] Pool sunucusu kontrol ediliyor: {POOL_URL}{R}")
    try:
        with urllib.request.urlopen(f"{POOL_URL}/api/stats", timeout=8) as r:
            d = json.loads(r.read())
            print(f"{G}[✓] Pool bağlantısı OK  |  "
                  f"Toplam NFT: {d.get('total_nfts',0)}  |  "
                  f"Worker: {d.get('active_workers',0)}{R}")
            return True
    except Exception as e:
        print(f"{Y}[!] Pool bağlantısı kurulamadı: {e}{R}")
        print(f"{Y}    Çalışmaya devam edilecek (offline mod){R}")
        return False

# ═══════════════════════════════════════════════════════════
#  ANA PROGRAM
# ═══════════════════════════════════════════════════════════
def main():
    banner()

    # 1. GPU Kontrolü
    check_nvidia()
    print()

    # 2. Pool Kontrolü
    check_pool()
    print()

    # 3. Kangaroo İndir
    bin_name = ensure_kangaroo()
    if not bin_name:
        print(f"{RE}[✗] Kangaroo indirilemedi, çıkılıyor.{R}")
        input("Çıkmak için Enter...")
        sys.exit(1)
    print()

    # 4. Puzzle Dosyasını Oluştur
    write_puzzle_file()
    print()

    # 5. Reporter Başlat
    t = threading.Thread(target=reporter_thread, daemon=True)
    t.start()
    print(f"{G}[✓] Pool reporter başlatıldı (her {REPORT_SECS}s'de rapor).{R}")
    print(f"{G}[✓] Kazanılan her NFT WAX hesabına mint edilecek: {BD}{WAX_ACCOUNT}{R}")
    print()

    print(f"{Y}{'─'*62}{R}")
    print(f"{BD}  Tarama başlıyor... Durdurmak için CTRL+C{R}")
    print(f"{Y}{'─'*62}{R}\n")

    # 6. Kangaroo'yu Çalıştır
    try:
        run_kangaroo(bin_name)
    except KeyboardInterrupt:
        print(f"\n\n{Y}[!] Durduruldu.{R}")
        elapsed = time.time() - _session_start
        hrs  = int(elapsed) // 3600
        mins = (int(elapsed) % 3600) // 60
        print(f"{C}  Çalışma süresi : {hrs:02d}:{mins:02d}{R}")
        print(f"{C}  Toplam Bkeys   : {_total_bkeys:,}{R}")
        print(f"{C}  Kazanılan NFT  : {_nfts_earned}{R}")

    input(f"\n{Y}Çıkmak için Enter...{R}")

if __name__ == "__main__":
    main()
