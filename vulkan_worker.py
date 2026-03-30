#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PUZZLE135 — GPU Worker v3.0
oritwoen/kangaroo — Vulkan/DX12/Metal
AMD / NVIDIA / Intel / Apple — CUDA gerekmez
"""

import os, sys, time, json, threading, subprocess, platform, re
import urllib.request, urllib.error, atexit, signal

WAX_ACCOUNT   = "__WAX_ACCOUNT__"
POOL_URL      = "__POOL_URL__"
GPU_TYPE      = "vulkan"
VERSION       = "3.0.0"
PUBKEY        = "02145d2611c823a396ef6712ce0f712f09b9b4f3135e3e0aa3230fb9b6d08d1e16"
RANGE_START   = "4000000000000000000000000000000000"
RANGE_BITS    = "135"
REPORT_SECS   = 30
NFT_THRESHOLD = 10000

# oritwoen/kangaroo binary adı
BIN = "kangaroo.exe" if platform.system() == "Windows" else "kangaroo"

IS_WIN = platform.system() == "Windows"
if IS_WIN: os.system("color")
R="\033[0m";G="\033[92m";Y="\033[93m";RE="\033[91m";C="\033[96m";M="\033[95m";W="\033[97m";BD="\033[1m"

def banner():
    os.system("cls" if IS_WIN else "clear")
    print(f"\n{M}{'='*62}{R}")
    print(f"{BD}  PUZZLE135  GPU Worker  v{VERSION}{R}")
    print(f"{M}{'─'*62}{R}")
    print(f"{C}  WAX  : {BD}{W}{WAX_ACCOUNT}{R}")
    print(f"{C}  Pool : {W}{POOL_URL}{R}")
    print(f"{C}  GPU  : {M}Vulkan/DX12 (AMD/NVIDIA/Intel — otomatik){R}")
    print(f"{M}{'─'*62}{R}")
    print(f"{G}  Her {NFT_THRESHOLD:,} Bkeys = 1 NFT  →  {WAX_ACCOUNT}{R}")
    print(f"{M}{'='*62}{R}\n")

def find_kangaroo():
    """kangaroo binary'sini bul — PATH veya mevcut klasör"""
    # Mevcut klasörde var mı?
    if os.path.exists(BIN):
        return f".\\{BIN}" if IS_WIN else f"./{BIN}"
    # PATH'te var mı? (cargo install ile kurulmuş)
    try:
        r = subprocess.run([BIN, "--version"], capture_output=True, timeout=5)
        if r.returncode == 0:
            return BIN
    except: pass
    # Cargo bin klasörü
    cargo_bin = os.path.expanduser(f"~/.cargo/bin/{BIN}")
    if os.path.exists(cargo_bin):
        return cargo_bin
    return None

def install_kangaroo():
    """Rust + kangaroo otomatik kur"""
    print(f"\n{Y}[i] Kangaroo bulunamadı. Otomatik kuruluyor...{R}")
    print(f"{Y}    Bu işlem 5-10 dakika sürer, bir kez yapılır.{R}\n")

    cargo_bin = os.path.expanduser("~/.cargo/bin")
    cargo_exe = os.path.join(cargo_bin, "cargo.exe" if IS_WIN else "cargo")

    # 1. Rust kurulu mu?
    if not os.path.exists(cargo_exe):
        print(f"{Y}[1/2] Rust indiriliyor...{R}")
        try:
            if IS_WIN:
                rustup_url = "https://static.rust-lang.org/rustup/dist/x86_64-pc-windows-msvc/rustup-init.exe"
                rustup_path = os.path.join(os.environ.get("TEMP", "."), "rustup-init.exe")
                urllib.request.urlretrieve(rustup_url, rustup_path)
                print(f"{Y}[1/2] Rust kuruluyor (sessiz mod)...{R}")
                subprocess.run([rustup_path, "-y", "--default-toolchain", "stable",
                               "--profile", "minimal"], check=True)
                os.remove(rustup_path)
            else:
                subprocess.run(
                    'curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal',
                    shell=True, check=True
                )
            # PATH güncelle
            os.environ["PATH"] = cargo_bin + os.pathsep + os.environ.get("PATH", "")
            print(f"{G}[✓] Rust kuruldu.{R}")
        except Exception as e:
            print(f"{RE}[✗] Rust kurulamadı: {e}{R}")
            return False

    # PATH güncelle
    os.environ["PATH"] = cargo_bin + os.pathsep + os.environ.get("PATH", "")

    # 2. Default toolchain ayarla
    rustup_exe = os.path.join(cargo_bin, "rustup.exe" if IS_WIN else "rustup")
    try:
        subprocess.run([rustup_exe, "default", "stable"], check=True)
        print(f"{G}[✓] Rust toolchain ayarlandı.{R}")
    except Exception as e:
        print(f"{Y}[!] Toolchain ayarlanamadı: {e}{R}")

    # 3. Kangaroo kur
    print(f"\n{Y}[2/2] Kangaroo GPU kuruluyor...{R}")
    try:
        subprocess.run([cargo_exe, "install", "kangaroo"], check=True)
        print(f"{G}[✓] Kangaroo GPU kuruldu!{R}")
        return True
    except Exception as e:
        print(f"{RE}[✗] Kangaroo kurulamadı: {e}{R}")
        return False

# ── POOL REPORTER ─────────────────────────────────────────
_lock=threading.Lock(); _pending=0; _total=0; _speed=0.0; _nfts=0; _start=time.time()

def reporter():
    global _pending, _nfts
    while True:
        time.sleep(REPORT_SECS)
        with _lock:
            bk=_pending; _pending=0
        if bk<=0: continue
        try:
            data=json.dumps({"wax_account":WAX_ACCOUNT,"bkeys":bk,
                "gpu_type":GPU_TYPE,"speed_mkeys":round(_speed,2),"version":VERSION}).encode()
            req=urllib.request.Request(f"{POOL_URL}/api/report",data=data,method="POST",
                headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req,timeout=15) as r:
                resp=json.loads(r.read())
            _nfts=resp.get("user_total_nfts",_nfts)
            new=resp.get("new_nfts_minted",0)
            until=resp.get("bkeys_until_next_nft",NFT_THRESHOLD)
            msg=f"\n{G}[✓] {bk:,} Bkeys | NFT: {_nfts}"
            if new>0: msg+=f" | {BD}+{new} NFT MINT! 🎉{R}{G}"
            msg+=f" | Sonraki: {until:,} Bkeys{R}"
            print(msg)
        except Exception as e:
            print(f"\n{Y}[!] Rapor gönderilemedi: {e}{R}")

def son_rapor():
    with _lock:
        bk=_pending
    if bk<=0: return
    try:
        data=json.dumps({"wax_account":WAX_ACCOUNT,"bkeys":bk,
            "gpu_type":GPU_TYPE,"speed_mkeys":round(_speed,2)}).encode()
        req=urllib.request.Request(f"{POOL_URL}/api/report",data=data,method="POST",
            headers={"Content-Type":"application/json"})
        urllib.request.urlopen(req,timeout=8)
    except: pass

atexit.register(son_rapor)
try:
    signal.signal(signal.SIGTERM, lambda s,f: sys.exit(0))
    signal.signal(signal.SIGINT,  lambda s,f: sys.exit(0))
except: pass

def time_per_nft(s):
    if s<=0: return "—"
    sec=(NFT_THRESHOLD*1000)/s
    if sec<60: return f"{int(sec)}s"
    if sec<3600: return f"{sec/60:.1f}m"
    if sec<86400: return f"{sec/3600:.1f}h"
    return f"{sec/86400:.1f}g"

def nfts_per_day(s):
    return (s*86400)/(NFT_THRESHOLD*1000) if s>0 else 0

def status(spd,bkt,nfts,elapsed):
    bar="█"*min(22,int(spd/50))+"░"*(22-min(22,int(spd/50)))
    h=int(elapsed)//3600;m=(int(elapsed)%3600)//60;s=int(elapsed)%60
    bk=f"{bkt/1e6:.1f}M" if bkt>=1e6 else f"{bkt//1000}K"
    npd=nfts_per_day(spd); nxt=time_per_nft(spd)
    rate=f"{npd:.1f}/gun" if npd>=1 else f"1/{nxt}"
    sys.stdout.write(
        f"\r{M}[⚡]{R} {spd:6.1f} Mkeys/s {C}[{bar}]{R} "
        f"NFT:{G}{nfts}{R}({Y}{rate}{R}) "
        f"Next:{G}{nxt}{R} "
        f"Bkeys:{W}{bk}{R} "
        f"{Y}{h:02d}:{m:02d}:{s:02d}{R}   "
    )
    sys.stdout.flush()

def run(kangaroo_bin):
    global _pending, _total, _speed

    # oritwoen/kangaroo komutu
    cmd = [
        kangaroo_bin,
        "--pubkey", PUBKEY,
        "--start",  RANGE_START,
        "--range",  RANGE_BITS,
    ]
    print(f"{C}[►] Komut: {' '.join(cmd)}{R}")
    print(f"{G}    GPU otomatik algılanacak (Vulkan/DX12/Metal){R}\n")

    log_f = open("kangaroo_log.txt", "w", buffering=1)
    try:
        proc = subprocess.Popen(cmd, stdout=log_f, stderr=log_f)
    except FileNotFoundError:
        print(f"{RE}[✗] {kangaroo_bin} çalıştırılamadı!{R}")
        log_f.close(); return
    except Exception as e:
        print(f"{RE}[✗] Hata: {e}{R}")
        log_f.close(); return

    print(f"{G}[✓] Kangaroo çalışıyor — log: kangaroo_log.txt{R}")
    print(f"{G}[✓] Rapor: her {REPORT_SECS}s{R}\n")
    time.sleep(3)

    last_pos = 0
    while True:
        time.sleep(0.3)
        try:
            with open("kangaroo_log.txt","r",errors="replace") as lf:
                lf.seek(last_pos)
                data=lf.read()
                last_pos=lf.tell()
        except: data=""

        for line in data.replace("\r","\n").split("\n"):
            line=line.strip()
            if not line: continue

            # oritwoen/kangaroo hız formatları:
            # "speed: 123.4 Mkeys/s" veya "123.4 MK/s" veya "[123.4 MKey/s]"
            m = re.search(r'([\d.]+)\s*([MBGKk])[Kk]?ey?s?/s', line, re.I)
            if m:
                val=float(m.group(1)); unit=m.group(2).upper()
                if unit=='K': val/=1000
                elif unit=='B': val*=1000
                elif unit=='G': val*=1_000_000
                _speed=val
                bk=int(val*0.3)
                with _lock:
                    _pending+=bk; _total+=bk
                status(val,_total,_nfts,time.time()-_start)
                continue

            # Çözüm bulundu
            ll=line.lower()
            if any(k in ll for k in ["found","private","key:","solved","0x"]):
                if any(c in line for c in ["0x","Found"]) or "key" in ll:
                    cozuldu(line); continue

            # Bilgi satırları
            if any(k in ll for k in ["gpu","vulkan","dx12","metal","error","device","backend","ops","dp"]):
                print(f"\n{Y}[i] {line}{R}")

        if proc.poll() is not None:
            log_f.close()
            print(f"\n{Y}[!] Kangaroo sona erdi (kod: {proc.returncode}).{R}")
            # Hata kodu varsa log son satırını göster
            if proc.returncode != 0:
                try:
                    with open("kangaroo_log.txt","r") as lf:
                        lines=[l.strip() for l in lf.readlines() if l.strip()]
                        for l in lines[-5:]:
                            print(f"  {RE}{l}{R}")
                except: pass
            break

def cozuldu(line):
    print(f"\n\n{G}{'★'*60}{R}")
    print(f"{BD}{G}  🎉 PUZZLE #135 ÇÖZÜLDÜ! 🎉{R}")
    print(f"{G}  {line}{R}")
    print(f"{G}{'★'*60}{R}\n")
    try:
        data=json.dumps({"wax_account":WAX_ACCOUNT,"line":line,"gpu_type":GPU_TYPE}).encode()
        req=urllib.request.Request(f"{POOL_URL}/api/solved",data=data,method="POST",
            headers={"Content-Type":"application/json"})
        urllib.request.urlopen(req,timeout=10)
        print(f"{G}[✓] Pool'a bildirildi!{R}")
    except: pass
    input(f"\n{Y}Enter'a bas...{R}")

def check_pool():
    try:
        with urllib.request.urlopen(f"{POOL_URL}/api/stats",timeout=10) as r:
            d=json.loads(r.read())
            print(f"{G}[✓] Pool OK | NFT: {d.get('total_nfts',0)} | Worker: {d.get('active_workers',0)}{R}")
    except Exception as e:
        print(f"{Y}[!] Pool bağlantısı yok: {e}{R}")

def main():
    banner()
    check_pool(); print()

    kangaroo_bin = find_kangaroo()
    if not kangaroo_bin:
        success = install_kangaroo()
        if success:
            # Kurulum bitti, tekrar bul
            kangaroo_bin = find_kangaroo()
        if not kangaroo_bin:
            print(f"\n{RE}[✗] Kangaroo bulunamadı. Lütfen manuel kur:{R}")
            print(f"{Y}    cargo install kangaroo{R}")
            input(f"\n{Y}Enter'a bas...{R}")
            sys.exit(1)

    print(f"{G}[✓] Kangaroo bulundu: {kangaroo_bin}{R}\n")

    threading.Thread(target=reporter, daemon=True).start()
    print(f"{G}[✓] Reporter başlatıldı (her {REPORT_SECS}s).{R}\n")
    print(f"{M}{'─'*62}{R}")
    print(f"{BD}  GPU taraması başlıyor... Durdurmak için CTRL+C{R}")
    print(f"{M}{'─'*62}{R}\n")

    try:
        run(kangaroo_bin)
    except KeyboardInterrupt:
        e=time.time()-_start; h=int(e)//3600; m=(int(e)%3600)//60
        print(f"\n\n{Y}Durduruldu. Süre:{h:02d}:{m:02d} Bkeys:{_total:,} NFT:{_nfts}{R}")

    input(f"\n{Y}Çıkmak için Enter...{R}")

if __name__=="__main__":
    main()
