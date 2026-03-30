'use strict';

// ============================================================
//  PUZZLE135 — Pool Server  v4.0
//  npm install express better-sqlite3 eosjs node-fetch@2 dotenv cors
// ============================================================

const express  = require('express');
const path     = require('path');
const fs       = require('fs');
const crypto   = require('crypto');
require('dotenv').config();

let Api, JsonRpc, JsSignatureProvider, fetch, Database;
try {
  ({ Api, JsonRpc }        = require('eosjs'));
  ({ JsSignatureProvider } = require('eosjs/dist/eosjs-jssig'));
  fetch                    = require('node-fetch');
  Database                 = require('better-sqlite3');
} catch (e) {
  console.error('Missing deps. Run: npm install');
  process.exit(1);
}

const PORT          = process.env.PORT           || 3000;
const CONTRACT      = process.env.CONTRACT_NAME  || 'puzzle135btc';
const ADMIN_ACCOUNT = process.env.ADMIN_ACCOUNT  || 'puzzle135btc';
const ADMIN_KEY     = process.env.ADMIN_KEY      || 'changeme';
const ADMIN_PRIVKEY = process.env.ADMIN_PRIVATE_KEY || '';
const POOL_URL      = process.env.POOL_URL       || '';
const NFT_THRESHOLD = 10000;

const rpc = new JsonRpc('https://wax.greymass.com', { fetch });
const api = ADMIN_PRIVKEY ? new Api({
  rpc,
  signatureProvider: new JsSignatureProvider([ADMIN_PRIVKEY]),
  textDecoder: new TextDecoder(),
  textEncoder: new TextEncoder()
}) : null;

const db = new Database(path.join(process.cwd(), 'puzzle135.db'));
db.exec(`
  CREATE TABLE IF NOT EXISTS contributors (
    wax_account TEXT PRIMARY KEY,
    bkeys_total INTEGER DEFAULT 0,
    nfts_minted INTEGER DEFAULT 0,
    last_seen   INTEGER DEFAULT 0,
    gpu_type    TEXT DEFAULT 'unknown'
  );
  CREATE TABLE IF NOT EXISTS pool (
    id INTEGER PRIMARY KEY DEFAULT 0,
    total_bkeys INTEGER DEFAULT 0,
    total_nfts  INTEGER DEFAULT 0,
    solved      INTEGER DEFAULT 0
  );
  CREATE TABLE IF NOT EXISTS mint_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wax_account TEXT,
    bkeys INTEGER,
    nfts INTEGER,
    tx_id TEXT,
    ts INTEGER
  );
  INSERT OR IGNORE INTO pool (id) VALUES (0);
`);

const getContrib  = db.prepare('SELECT * FROM contributors WHERE wax_account = ?');
const saveContrib = db.prepare(`
  INSERT INTO contributors (wax_account,bkeys_total,nfts_minted,last_seen,gpu_type)
  VALUES (@wax_account,@bkeys_total,@nfts_minted,@last_seen,@gpu_type)
  ON CONFLICT(wax_account) DO UPDATE SET
    bkeys_total=@bkeys_total,nfts_minted=@nfts_minted,
    last_seen=@last_seen,gpu_type=@gpu_type
`);
const getPool    = db.prepare('SELECT * FROM pool WHERE id = 0');
const updatePool = db.prepare('UPDATE pool SET total_bkeys=?,total_nfts=? WHERE id=0');
const addLog     = db.prepare('INSERT INTO mint_log(wax_account,bkeys,nfts,tx_id,ts) VALUES(?,?,?,?,?)');

const heartbeat = {};

// Daily bonus system removed
const sessions  = new Map();
const failedLogins = new Map();

const app = express();
app.use(require('cors')());
app.use(express.json());

// Cookie parser
app.use((req, res, next) => {
  req.cookies = {};
  const h = req.headers.cookie;
  if (h) h.split(';').forEach(c => {
    const [k, ...v] = c.trim().split('=');
    if (k) req.cookies[k.trim()] = v.join('=').trim();
  });
  next();
});

function checkSession(req) {
  const token = req.cookies.admin_session;
  if (!token) return false;
  const s = sessions.get(token);
  if (!s || Date.now() > s.expiresAt) { sessions.delete(token); return false; }
  return true;
}

// ── ADMIN LOGIN PAGE ──────────────────────────────────────
app.get('/admin-login', (req, res) => {
  if (checkSession(req)) return res.redirect('/admin');
  res.send(`<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>Admin - PUZZLE135</title>
<style>*{box-sizing:border-box;margin:0;padding:0}
body{background:#030712;color:#e2e8f0;font-family:system-ui,sans-serif;
min-height:100vh;display:flex;align-items:center;justify-content:center}
.c{background:#0f172a;border:1px solid #1e293b;border-radius:16px;padding:2.5rem;width:360px;text-align:center}
h1{color:#f7c948;font-size:1.2rem;margin-bottom:.5rem}p{color:#64748b;font-size:.82rem;margin-bottom:2rem}
input{width:100%;background:#1e293b;border:1px solid #334155;color:#e2e8f0;
padding:.8rem 1rem;border-radius:8px;font-size:1rem;outline:none;margin-bottom:1rem;letter-spacing:.15em}
input:focus{border-color:#f7c948}
button{width:100%;background:#f7c948;color:#030712;border:none;padding:.85rem;
border-radius:8px;font-weight:700;font-size:1rem;cursor:pointer}
button:hover{opacity:.88}button:disabled{opacity:.5}
.err{color:#f87171;font-size:.82rem;margin-top:.8rem;display:none}</style></head>
<body><div class="c"><h1>PUZZLE135 Admin</h1><p>Authorized access only</p>
<input type="password" id="pw" placeholder="Password" onkeydown="if(event.key==='Enter')login()">
<button onclick="login()" id="btn">Login</button>
<div class="err" id="err"></div></div>
<script>async function login(){
const pw=document.getElementById('pw').value.trim();if(!pw)return;
const btn=document.getElementById('btn'),err=document.getElementById('err');
btn.disabled=true;btn.textContent='...';err.style.display='none';
try{const r=await fetch('/api/admin/login',{method:'POST',
headers:{'Content-Type':'application/json'},body:JSON.stringify({key:pw})});
const d=await r.json();
if(d.ok)window.location.href='/admin';
else{err.textContent=d.error||'Wrong password';err.style.display='block';}
}catch(e){err.textContent='Server error';err.style.display='block';}
btn.disabled=false;btn.textContent='Login';}</script></body></html>`);
});

// ── ADMIN PANEL ───────────────────────────────────────────
app.get('/admin', (req, res) => {
  if (!checkSession(req)) return res.redirect('/admin-login');
  const f = path.join(process.cwd(), 'admin.html');
  if (fs.existsSync(f)) return res.sendFile(f);
  res.send('<h2 style="color:#f7c948;font-family:monospace;padding:2rem">admin.html not found in ' + process.cwd() + '</h2>');
});

app.get('/admin.html', (req, res) => res.redirect('/admin-login'));

// ── POST /api/admin/login ─────────────────────────────────
app.post('/api/admin/login', (req, res) => {
  const ip   = req.ip;
  const fail = failedLogins.get(ip) || { count: 0, bannedUntil: 0 };

  if (fail.bannedUntil > Date.now()) {
    const mins = Math.ceil((fail.bannedUntil - Date.now()) / 60000);
    return res.status(429).json({ ok: false, error: `Too many attempts. Wait ${mins} min.` });
  }

  const { key } = req.body;
  if (!key || key !== ADMIN_KEY) {
    fail.count++;
    if (fail.count >= 5) { fail.bannedUntil = Date.now() + 15*60*1000; fail.count = 0; }
    failedLogins.set(ip, fail);
    return setTimeout(() => res.status(401).json({ ok:false, error:'Wrong password' }), 1200);
  }

  failedLogins.delete(ip);
  const token = crypto.randomBytes(48).toString('hex');
  sessions.set(token, { expiresAt: Date.now() + 8*3600*1000 });
  res.setHeader('Set-Cookie', `admin_session=${token}; HttpOnly; SameSite=Strict; Max-Age=${8*3600}; Path=/`);
  res.json({ ok: true });
});

// Admin API middleware
app.use('/api/admin', (req, res, next) => {
  if (req.path === '/login') return next();
  if (!checkSession(req)) return res.status(401).json({ error:'Not authenticated' });
  next();
});

// ── POST /api/report ──────────────────────────────────────
app.post('/api/report', async (req, res) => {
  const { wax_account, bkeys, gpu_type = 'unknown' } = req.body;
  if (!wax_account || typeof wax_account !== 'string')
    return res.status(400).json({ error: 'wax_account required' });
  if (!bkeys || typeof bkeys !== 'number' || bkeys <= 0 || bkeys > 50000)
    return res.status(400).json({ error: 'bkeys must be 1-50000' });

  heartbeat[wax_account] = Date.now();

  const c           = getContrib.get(wax_account);
  const prev_bkeys  = c ? c.bkeys_total : 0;
  const prev_minted = c ? c.nfts_minted : 0;
  const new_bkeys   = prev_bkeys + bkeys;
  const nfts_to_mint = Math.floor(new_bkeys / NFT_THRESHOLD) - prev_minted;
  const new_minted  = prev_minted + nfts_to_mint;

  saveContrib.run({ wax_account, bkeys_total:new_bkeys, nfts_minted:new_minted,
    last_seen:Date.now(), gpu_type });

  const pool = getPool.get();
  updatePool.run(pool.total_bkeys + bkeys, pool.total_nfts + nfts_to_mint);

  let tx_id = null;
  if (nfts_to_mint > 0) {
    console.log(`[MINT] ${wax_account} → ${nfts_to_mint} NFT`);
    try {
      tx_id = await mintOnChain(wax_account, bkeys, nfts_to_mint);
      addLog.run(wax_account, new_bkeys, nfts_to_mint, tx_id, Date.now());
      console.log(`[MINT ✓] ${wax_account} → ${nfts_to_mint} NFT | TX: ${tx_id}`);
    } catch (e) {
      // Mint başarısız — Bkeys kaydedildi ama NFT sayısı önceki değerde kalır
      // Bir sonraki raporda tekrar hesaplanacak
      console.error(`[MINT ✗] ${wax_account}: ${e.message}`);
      saveContrib.run({ wax_account, bkeys_total:new_bkeys, nfts_minted:prev_minted,
        last_seen:Date.now(), gpu_type });
      // Kullanıcıya hata döndürme — sessizce devam et, bir sonraki raporda tekrar denenecek
    }
  }

  const p2 = getPool.get();
  res.json({
    ok:true, wax_account,
    bkeys_this_report: bkeys,
    bkeys_total: new_bkeys,
    bkeys_until_next_nft: NFT_THRESHOLD - (new_bkeys % NFT_THRESHOLD),
    new_nfts_minted: nfts_to_mint,
    user_total_nfts: new_minted,
    tx_id,
    pool: { total_bkeys: p2.total_bkeys, total_nfts: p2.total_nfts }
  });
});

async function mintOnChain(waxAccount, bkeys, nfts) {
  if (!api) { console.log(`[SIM] ${waxAccount} → ${nfts} NFT`); return 'sim-'+Date.now(); }
  const r = await api.transact({ actions:[{
    account: CONTRACT, name:'mintnft',
    authorization:[{ actor:ADMIN_ACCOUNT, permission:'active' }],
    data:{ minter:ADMIN_ACCOUNT, to_account:waxAccount, bkeys, nfts_to_mint:nfts }
  }]}, { blocksBehind:3, expireSeconds:30 });
  return r.transaction_id;
}

// ── GET /api/stats ────────────────────────────────────────
app.get('/api/stats', (req, res) => {
  const pool   = getPool.get();
  const cutoff = Date.now() - 5*60*1000;
  const active = Object.values(heartbeat).filter(t => t > cutoff).length;
  res.json({ total_nfts:pool.total_nfts, total_bkeys:pool.total_bkeys,
    active_workers:active, nft_threshold:NFT_THRESHOLD, solved:pool.solved===1 });
});

// ── GET /api/leaderboard ──────────────────────────────────
app.get('/api/leaderboard', (req, res) => {
  const total = getPool.get().total_nfts || 1;
  const rows  = db.prepare(`SELECT wax_account,nfts_minted,bkeys_total,gpu_type
    FROM contributors ORDER BY nfts_minted DESC LIMIT 50`).all();
  res.json(rows.map((r,i) => ({
    rank:i+1, account:r.wax_account, nft_count:r.nfts_minted,
    bkeys_total:r.bkeys_total, gpu_type:r.gpu_type,
    share_pct:((r.nfts_minted/total)*100).toFixed(4)
  })));
});

// ── GET /api/user/:account ────────────────────────────────
app.get('/api/user/:account', (req, res) => {
  const total = getPool.get().total_nfts || 1;
  const c     = getContrib.get(req.params.account);
  if (!c) return res.json({ nft_count:0, bkeys_total:0, share_pct:'0',
    bkeys_until_next_nft:NFT_THRESHOLD });
  res.json({ wax_account:c.wax_account, nft_count:c.nfts_minted,
    bkeys_total:c.bkeys_total,
    bkeys_until_next_nft: NFT_THRESHOLD - (c.bkeys_total % NFT_THRESHOLD),
    gpu_type:c.gpu_type, share_pct:((c.nfts_minted/total)*100).toFixed(4) });
});

// ── POST /api/solved ──────────────────────────────────────
app.post('/api/solved', async (req, res) => {
  const { wax_account, line } = req.body;
  console.log('\n🎉🎉🎉 PUZZLE COZULDU! 🎉🎉🎉');
  console.log('WAX:', wax_account);
  console.log('Key:', line);
  db.prepare('UPDATE pool SET solved=1 WHERE id=0').run();

  // Telegram bildirimi
  const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
  const CHAT_ID   = process.env.TELEGRAM_CHAT_ID;

  if (BOT_TOKEN && CHAT_ID) {
    const msg = `🎉🎉🎉 PUZZLE #135 ÇÖZÜLDÜ! 🎉🎉🎉

💎 Private Key:
${line}

👤 Bulan: ${wax_account}
⏰ Zaman: ${new Date().toISOString()}

🚨 HEMEN HAREKET ET:
1. Private key'i Electrum'a gir
2. 13 BTC'yi al
3. WAXP'a çevir
4. puzzle135btc'ye "reward" memo ile gönder`;

    try {
      await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`, {
        method : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body   : JSON.stringify({
          chat_id    : CHAT_ID,
          text       : msg,
          parse_mode : 'HTML'
        })
      });
      console.log('[TELEGRAM] Bildirim gönderildi!');
    } catch(e) {
      console.error('[TELEGRAM] Hata:', e.message);
    }

    // 30 saniyede bir tekrar gönder (3 kez) — kaçırma ihtimaline karşı
    let count = 0;
    const repeat = setInterval(async () => {
      count++;
      try {
        await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`, {
          method : 'POST',
          headers: { 'Content-Type': 'application/json' },
          body   : JSON.stringify({
            chat_id: CHAT_ID,
            text   : `🔔 HATIRLATMA (${count}/3): Puzzle çözüldü! Private key: ${line}`
          })
        });
      } catch {}
      if (count >= 3) clearInterval(repeat);
    }, 30000);
  } else {
    console.warn('[TELEGRAM] BOT_TOKEN veya CHAT_ID eksik!');
  }

  res.json({ ok: true });
});

// ── POST /api/admin/gift — Manuel NFT Hediye ────────────────
app.post('/api/admin/gift', async (req, res) => {
  if (!checkSession(req)) return res.status(401).json({ error:'Not authenticated' });
  const { wax_account, amount, reason } = req.body;
  if (!wax_account) return res.status(400).json({ error:'wax_account required' });
  const nfts = Math.min(1000, Math.max(1, parseInt(amount)||1));

  const contrib = getContrib.get(wax_account);
  const pool    = getPool.get();
  saveContrib.run({
    wax_account,
    bkeys_total : contrib ? contrib.bkeys_total : 0,
    nfts_minted : (contrib ? contrib.nfts_minted : 0) + nfts,
    last_seen   : Date.now(),
    gpu_type    : contrib ? contrib.gpu_type : 'gift'
  });
  updatePool.run(pool.total_bkeys, pool.total_nfts + nfts);

  let tx_id = 'sim-gift-' + Date.now();
  if (api) {
    try { tx_id = await mintOnChain(wax_account, 0, nfts); }
    catch(e) { return res.status(500).json({ error:'Mint failed: '+e.message }); }
  }
  addLog.run(wax_account, 0, nfts, tx_id, Date.now());
  console.log(`[GIFT] ${wax_account} → +${nfts} NFT | ${reason||'manuel'}`);
  res.json({ ok:true, wax_account, nfts_gifted:nfts, tx_id });
});


// ── GET /api/admin/stats ──────────────────────────────────
app.get('/api/admin/stats', (req, res) => {
  const pool  = getPool.get();
  const users = db.prepare('SELECT * FROM contributors ORDER BY nfts_minted DESC').all();
  const logs  = db.prepare('SELECT * FROM mint_log ORDER BY id DESC LIMIT 100').all();
  res.json({ pool, contributors:users, recent_mints:logs });
});

// ── GET /api/download/worker ──────────────────────────────
app.get('/api/download/worker', (req, res) => {
  const { wax, type, format } = req.query;
  if (!wax) return res.status(400).json({ error:'wax parameter required' });

  // Artık tek evrensel worker var
  const pool   = POOL_URL || process.env.POOL_URL || '';

  // ── Windows BAT launcher (hiç kurulum gerektirmez) ────
  if (format === 'bat' || format === 'win') {
    const batName = isCuda ? 'PUZZLE135-CUDA-Worker.bat' : 'PUZZLE135-Vulkan-Worker.bat';
    const workerUrl = `${pool}/api/download/worker?wax=${encodeURIComponent(wax)}&type=${isCuda?'cuda':'vulkan'}&format=py`;
    const bat = `@echo off
chcp 65001 >nul 2>&1
title PUZZLE135 - ${isCuda?'CUDA':'Vulkan'} Worker
color 0A

echo.
echo ═══════════════════════════════════════════════════
echo    PUZZLE135 - ${isCuda?'CUDA (NVIDIA)':'Vulkan (AMD/Intel)'} Worker
echo    WAX: ${wax}
echo ═══════════════════════════════════════════════════
echo.

:: Python kontrol
python --version >nul 2>&1
if %errorlevel% == 0 (set PY=python & goto RUN)
py --version >nul 2>&1
if %errorlevel% == 0 (set PY=py & goto RUN)

echo [!] Python bulunamadi. Yukleniyor (bir kereligine, ~1 dakika)...
curl -L -o "%TEMP%\pysetup.exe" "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
"%TEMP%\pysetup.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
del "%TEMP%\pysetup.exe" >nul 2>&1
set PY=python
echo [OK] Python kuruldu.
echo.

:RUN
if not exist "worker.py" (
  echo [Indiriliyor] Worker dosyasi aliniyor...
  curl -L -o "worker.py" "${workerUrl}"
  echo [OK] Hazir.
  echo.
)
%PY% worker.py
if %errorlevel% neq 0 pause
`;
    res.setHeader('Content-Disposition', `attachment; filename="${batName}"`);
    res.setHeader('Content-Type', 'text/plain; charset=utf-8');
    return res.send(bat);
  }

  // ── Python dosyası ────────────────────────────────────
  // worker.py veya vulkan_worker.py'yi ara
  const srcName = fs.existsSync(path.join(process.cwd(), 'worker.py'))
    ? 'worker.py' : 'vulkan_worker.py';
  const outName = 'PUZZLE135-Worker.py';
  const srcPath = path.join(process.cwd(), srcName);

  if (!fs.existsSync(srcPath)) {
    const files = fs.readdirSync(process.cwd());
    return res.status(404).json({ error:'Worker file not found', cwd:process.cwd(), files });
  }

  let src = fs.readFileSync(srcPath, 'utf8');
  src = src.replace('__WAX_ACCOUNT__', wax)
           .replace('__POOL_URL__', pool);

  res.setHeader('Content-Disposition', `attachment; filename="${outName}"`);
  res.setHeader('Content-Type', 'text/plain; charset=utf-8');
  res.send(src);
});

// ── GET /api/download/setup — GPU Setup BAT ─────────────────
app.get('/api/download/setup', (req, res) => {
  const { wax } = req.query;
  if (!wax) return res.status(400).json({ error: 'wax parameter required' });

  const batPath = path.join(process.cwd(), 'PUZZLE135-GPU-Setup.bat');
  if (!fs.existsSync(batPath)) {
    return res.status(404).json({ error: 'Setup file not found' });
  }

  let bat = fs.readFileSync(batPath, 'utf8');
  // WAX hesabını inject et
  bat = bat.replace(/__WAX__/g, wax)
           .replace(/__POOL_URL__/g, POOL_URL);

  res.setHeader('Content-Disposition', 'attachment; filename="PUZZLE135-GPU-Setup.bat"');
  res.setHeader('Content-Type', 'text/plain; charset=utf-8');
  res.send(bat);
});

// ── GET /api/prices — CoinGecko Proxy ───────────────────
let priceCache = { data: null, ts: 0 };

app.get('/api/prices', async (req, res) => {
  // 60 saniye cache
  if (priceCache.data && Date.now() - priceCache.ts < 60000) {
    return res.json(priceCache.data);
  }
  try {
    const r = await fetch(
      'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,wax&vs_currencies=usd',
      { headers: { 'Accept': 'application/json' }, timeout: 8000 }
    );
    const data = await r.json();
    priceCache = { data, ts: Date.now() };
    res.json(data);
  } catch(e) {
    // Cache varsa eski veriyi döndür
    if (priceCache.data) return res.json(priceCache.data);
    res.json({ bitcoin: { usd: 95000 }, wax: { usd: 0.05 } });
  }
});

// ── POST /api/ai — Anthropic Proxy ───────────────────────
// Rate limit: IP başına günlük 4 istek
const aiUsage = new Map(); // ip → { count, date }

function getAIRemaining(ip) {
  const today = new Date().toDateString();
  const entry = aiUsage.get(ip);
  if (!entry || entry.date !== today) return 4;
  return Math.max(0, 4 - entry.count);
}

function incAIUsage(ip) {
  const today = new Date().toDateString();
  const entry = aiUsage.get(ip) || { count: 0, date: today };
  if (entry.date !== today) { entry.count = 0; entry.date = today; }
  entry.count++;
  aiUsage.set(ip, entry);
}

app.post('/api/ai', async (req, res) => {
  const ip = req.ip;
  const remaining = getAIRemaining(ip);

  if (remaining <= 0) {
    return res.status(429).json({ error: 'Daily limit reached. Try again tomorrow.' });
  }

  const { messages, system } = req.body;
  if (!messages || !Array.isArray(messages)) {
    return res.status(400).json({ error: 'messages required' });
  }

  const ANTHROPIC_KEY = process.env.ANTHROPIC_API_KEY;
  if (!ANTHROPIC_KEY) {
    return res.status(500).json({ error: 'AI not configured' });
  }

  try {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type'      : 'application/json',
        'x-api-key'         : ANTHROPIC_KEY,
        'anthropic-version' : '2023-06-01'
      },
      body: JSON.stringify({
        model     : 'claude-haiku-4-5-20251001',
        max_tokens: 500,
        system    : system || '',
        messages  : messages.slice(-10) // son 10 mesaj
      })
    });

    const data = await response.json();

    if (!response.ok) {
      return res.status(500).json({ error: data.error?.message || 'AI error' });
    }

    incAIUsage(ip);
    res.json({
      content  : data.content,
      remaining: getAIRemaining(ip)
    });
  } catch(e) {
    res.status(500).json({ error: e.message });
  }
});

// ── STATIC ────────────────────────────────────────────────
const publicDir = path.join(process.cwd(), 'public');
if (fs.existsSync(publicDir)) app.use(express.static(publicDir));

app.use((req, res) => res.status(404).json({ error:'Not found' }));

// ── START ─────────────────────────────────────────────────
app.listen(PORT, () => {
  const pool = getPool.get();
  console.log(`PUZZLE135 Pool Server v4.0`);
  console.log(`Port    : ${PORT}`);
  console.log(`Contract: ${CONTRACT}`);
  console.log(`WAX API : ${api ? 'ACTIVE' : 'SIMULATED'}`);
  console.log(`NFTs    : ${pool.total_nfts} | Bkeys: ${pool.total_bkeys}`);
});
