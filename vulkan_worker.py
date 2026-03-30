#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PUZZLE135 — Vulkan Worker v2.1
Log dosyasından okuma — pipe sorunu yok
"""

import os, sys, time, json, threading, subprocess, platform, re
import urllib.request, urllib.error

WAX_ACCOUNT   = "__WAX_ACCOUNT__"
POOL_URL      = "__POOL_URL__"
GPU_TYPE      = "vulkan"
VERSION       = "2.1.0"
PUBKEY        = "02145d2611c823a396ef6712ce0f712f09b9b4f3135e3e0aa3230fb9b6d08d1e16"
RANGE_START   = "4000000000000000000000000000000000"
RANGE_END     = "7fffffffffffffffffffffffffffffffff"
REPORT_SECS   = 30
NFT_THRESHOLD = 10000
BIN           = "kangaroo.exe"
LOG_FILE      = "kangaroo_log.txt"
DL_URL        = "https://github.com/JeanLucPons/Kangaroo/releases/download/1.0/Kangaroo.exe"

IS_WIN = platform.system() == "Windows"
if IS_WIN: os.system("color")

# ── Pencere kapanınca bile çalışır ────────────────────────
import atexit, signal

def _send_final_report():
    global _bkeys_pending
    with _lock:
        bk = _bkeys_pending
        _bkeys_pending = 0
    if bk <= 0 or not POOL_URL or '__' in POOL_URL:
        return
    try:
        data = json.dumps({"wax_account":WAX_ACCOUNT,"bkeys":bk,
            "gpu_type":GPU_TYPE,"speed_mkeys":round(_speed,2)}).encode()
        req = urllib.request.Request(f"{POOL_URL}/api/report",data=data,method="POST",
            headers={"Content-Type":"application/json"})
        urllib.request.urlopen(req, timeout=8)
    except:
        pass

atexit.register(_send_final_report)

def _signal_handler(sig, frame):
    _send_final_report()
    sys.exit(0)

try:
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT,  _signal_handler)
except:
    pass
R="\033[0m";G="\033[92m";Y="\033[93m";RE="\033[91m";C="\033[96m";M="\033[95m";W="\033[97m";BD="\033[1m"

def banner():
    os.system("cls" if IS_WIN else "clear")
    print(f"\n{M}{'='*62}{R}")
    print(f"{BD}  PUZZLE135  Vulkan Worker  v{VERSION}{R}")
    print(f"{M}{'─'*62}{R}")
    print(f"{C}  WAX  : {BD}{W}{WAX_ACCOUNT}{R}")
    print(f"{C}  Pool : {W}{POOL_URL}{R}")
    print(f"{M}{'─'*62}{R}")
    print(f"{G}  Her {NFT_THRESHOLD:,} Bkeys = 1 NFT{R}")
    print(f"{M}{'='*62}{R}\n")

def download_kangaroo():
    if os.path.exists(BIN):
        print(f"{G}[✓] Kangaroo mevcut: {BIN}{R}"); return True
    print(f"{Y}[↓] Kangaroo indiriliyor...{R}")
    try:
        done=[False]
        def prog(b,bs,tot):
            if tot>0 and not done[0]:
                pct=min(100,b*bs*100//tot)
                bar="█"*(pct//4)+"░"*(25-pct//4)
                sys.stdout.write(f"\r    [{bar}] {pct}%  "); sys.stdout.flush()
                if pct>=100: done[0]=True
        urllib.request.urlretrieve(DL_URL, BIN, reporthook=prog)
        print(f"\n{G}[✓] İndirildi.{R}"); return True
    except Exception as e:
        print(f"\n{RE}[✗] Hata: {e}{R}"); return False

_lock=threading.Lock(); _bkeys_pending=0; _total_bkeys=0; _speed=0.0; _nfts=0; _start=time.time()

def reporter():
    global _bkeys_pending, _nfts
    while True:
        time.sleep(REPORT_SECS)
        with _lock:
            bk=_bkeys_pending; _bkeys_pending=0
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
            msg=f"\n{G}[✓] Rapor → {bk:,} Bkeys | NFT: {_nfts}"
            if new>0: msg+=f" | {BD}+{new} NFT MINT!{R}"
            msg+=f" | Sonraki: {until:,} Bkeys{R}"
            print(msg)
        except Exception as e:
            print(f"\n{Y}[!] Rapor gönderilemedi: {e}{R}")

def time_per_nft(s):
    if s<=0: return "—"
    sec=(NFT_THRESHOLD*1000)/s
    if sec<60: return f"{int(sec)}s"
    if sec<3600: return f"{sec/60:.1f}m"
    return f"{sec/3600:.1f}h"

def nfts_per_day(s):
    return (s*86400)/(NFT_THRESHOLD*1000) if s>0 else 0

def status(spd,bkt,nfts,elapsed):
    bar="█"*min(24,int(spd/50))+"░"*(24-min(24,int(spd/50)))
    h=int(elapsed)//3600; m=(int(elapsed)%3600)//60; s=int(elapsed)%60
    bk=f"{bkt/1e6:.1f}M" if bkt>=1e6 else f"{bkt//1000}K"
    npd=nfts_per_day(spd); nxt=time_per_nft(spd)
    rate=f"{npd:.1f}/day" if npd>=1 else f"1/{nxt}"
    sys.stdout.write(f"\r{M}[⚡]{R} {spd:6.1f} Mkeys/s {C}[{bar}]{R} NFT:{G}{nfts}{R}({Y}{rate}{R}) Next:{G}{nxt}{R} Bkeys:{W}{bk}{R} {Y}{h:02d}:{m:02d}:{s:02d}{R}   ")
    sys.stdout.flush()

def solved(line):
    print(f"\n\n{G}{'★'*60}{R}\n{BD}{G}  PUZZLE #135 ÇÖZÜLDÜ!{R}\n{G}  {line}{R}\n{G}{'★'*60}{R}\n")
    try:
        data=json.dumps({"wax_account":WAX_ACCOUNT,"line":line,"gpu_type":GPU_TYPE}).encode()
        req=urllib.request.Request(f"{POOL_URL}/api/solved",data=data,method="POST",
            headers={"Content-Type":"application/json"})
        urllib.request.urlopen(req,timeout=10)
        print(f"{G}[✓] Pool'a bildirildi!{R}")
    except Exception as e:
        print(f"{RE}[!] Hata: {e} — Private key'i sakla!{R}")
    input(f"\n{Y}Enter'a bas...{R}")

def run_kangaroo():
    global _bkeys_pending,_total_bkeys,_speed

    # Puzzle dosyası
    with open("puzzle135.txt","w") as f:
        f.write(f"{RANGE_START}\n{RANGE_END}\n{PUBKEY}\n")
    print(f"{G}[✓] puzzle135.txt oluşturuldu.{R}")

    cmd=[BIN,"puzzle135.txt"]
    print(f"\n{C}[►] Başlatılıyor: {' '.join(cmd)}{R}")

    # Log dosyasına yönlendir
    log_f=open(LOG_FILE,"w",buffering=1)
    try:
        proc=subprocess.Popen(cmd,stdout=log_f,stderr=log_f)
    except FileNotFoundError:
        print(f"{RE}[✗] {BIN} bulunamadı!{R}")
        log_f.close(); return

    print(f"{G}[✓] Kangaroo başlatıldı — log: {LOG_FILE}{R}")
    print(f"{G}[✓] Pool raporları {REPORT_SECS}s'de bir gönderiliyor.{R}\n")
    time.sleep(2)

    last_pos=0
    while True:
        time.sleep(0.5)

        # Log dosyasını oku
        try:
            with open(LOG_FILE,"r",errors="replace") as lf:
                lf.seek(last_pos)
                data=lf.read()
                last_pos=lf.tell()
        except: data=""

        for line in data.replace("\r","\n").split("\n"):
            line=line.strip()
            if not line: continue

            # Hız
            m=re.search(r'\[([\d.]+)\s*([MBGKk])Key/s\]',line,re.I)
            if m:
                val=float(m.group(1)); unit=m.group(2).upper()
                if unit=='K': val/=1000
                elif unit=='B': val*=1000
                elif unit=='G': val*=1_000_000
                _speed=val
                bk=int(val*0.5)
                with _lock:
                    _bkeys_pending+=bk; _total_bkeys+=bk
                status(val,_total_bkeys,_nfts,time.time()-_start)
                continue

            # Çözüm
            ll=line.lower()
            if any(k in ll for k in ["priv","pkey","key found","solved","winner"]):
                solved(line); continue

            # Bilgi
            if any(k in ll for k in ["start:","stop:","keys:","thread","range","error","dp size"]):
                print(f"\n{Y}[i] {line}{R}")

        # Bitti mi?
        if proc.poll() is not None:
            log_f.close()
            print(f"\n{Y}[!] Kangaroo sona erdi (kod: {proc.returncode}).{R}")
            break

def check_pool():
    try:
        with urllib.request.urlopen(f"{POOL_URL}/api/stats",timeout=10) as r:
            d=json.loads(r.read())
            print(f"{G}[✓] Pool OK  |  NFT: {d.get('total_nfts',0)}  |  Worker: {d.get('active_workers',0)}{R}")
    except Exception as e:
        print(f"{Y}[!] Pool bağlantısı yok: {e} — Offline mod.{R}")

def main():
    banner()
    check_pool(); print()
    if not download_kangaroo():
        input(f"{RE}Çıkmak için Enter...{R}"); sys.exit(1)
    print()
    threading.Thread(target=reporter,daemon=True).start()
    print(f"{G}[✓] Reporter başlatıldı (her {REPORT_SECS}s).{R}\n")
    print(f"{M}{'─'*62}{R}")
    print(f"{BD}  Tarama başlıyor... Durdurmak için CTRL+C{R}")
    print(f"{M}{'─'*62}{R}\n")
    try:
        run_kangaroo()
    except KeyboardInterrupt:
        e=time.time()-_start; h=int(e)//3600; m=(int(e)%3600)//60
        print(f"\n\n{Y}Durduruldu. Süre:{h:02d}:{m:02d} Bkeys:{_total_bkeys:,} NFT:{_nfts}{R}")
        # Bekleyen Bkeys'i pool'a gönder
        with _lock:
            bk=_bkeys_pending; _bkeys_pending=0
        if bk>0:
            print(f"{Y}[i] Kalan {bk:,} Bkeys pool'a gönderiliyor...{R}")
            try:
                data=json.dumps({"wax_account":WAX_ACCOUNT,"bkeys":bk,
                    "gpu_type":GPU_TYPE,"speed_mkeys":round(_speed,2)}).encode()
                req=urllib.request.Request(f"{POOL_URL}/api/report",data=data,method="POST",
                    headers={"Content-Type":"application/json"})
                with urllib.request.urlopen(req,timeout=10) as r:
                    resp=json.loads(r.read())
                print(f"{G}[✓] Son rapor gönderildi. NFT: {resp.get('user_total_nfts',0)}{R}")
            except Exception as ex:
                print(f"{RE}[!] Son rapor gönderilemedi: {ex}{R}")
    input(f"\n{Y}Çıkmak için Enter...{R}")

if __name__=="__main__":
    main()
