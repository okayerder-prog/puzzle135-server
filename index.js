// ============================================================
//  PUZZLE135 — Pool Server
//  Node.js + Express + SQLite
//
//  ✅ NASIL ÇALIŞIR:
//
//  1) Worker çalışır, 30sn'de bir pool'a rapor gönderir:
//     POST /api/report  { wax_account, bkeys: 150 }
//
//  2) Sunucu birikimli bkeys sayar (SQLite'da kalıcı):
//     myaccount.wax → 50 + 150 = 200 Bkeys birikti
//
//  3) Her 100 Bkeys geçildiğinde → 1 NFT mint edilir:
//     200 Bkeys → 2 NFT  (WAX smart contract'a gönderilir)
//     Bir sonraki raporda 0 NFT (200-220 = 20 Bkeys kaldı)
//
//  4) Worker 300 Bkeys daha rapor eder:
//     20 (kalan) + 300 = 320 Bkeys → 3 NFT daha mint
//     Kalan = 20
//
//  FORMÜL:
//     yeni_nft = floor(toplam_bkeys / 100) - önceki_mint_sayısı
//
// ============================================================

'use strict';

const express    = require('express');
const path       = require('path');
const fs         = require('fs');
require('dotenv').config();

// ── BAĞIMLILIKLAR ─────────────────────────────────────────
// npm install express eosjs better-sqlite3 node-fetch cors dotenv
let Api, JsonRpc, JsSignatureProvider, fetch, Database;
try {
  ({ Api, JsonRpc }         = require('eosjs'));
  ({ JsSignatureProvider }  = require('eosjs/dist/eosjs-jssig'));
  fetch                     = require('node-fetch');
  Database                  = require('better-sqlite3');
} catch (e) {
  console.error('Bağımlılıklar eksik. Çalıştır: npm install express eosjs better-sqlite3 node-fetch cors dotenv');
  process.exit(1);
}

const app = express();
app.use(require('cors')());
app.use(express.json());
// ═══════════════════════════════════════════════════════════
//  ADMIN GÜVENLİK SİSTEMİ
//  - Brute force koruması (5 yanlış → 15dk ban)
//  - Session token (giriş sonrası 8 saatlik oturum)
//  - admin.html URL'den direkt erişilemez
//  - Her istek session kontrolünden geçer
// ═══════════════════════════════════════════════════════════

const crypto = require('crypto');

// Aktif sessionlar: { token: { ip, expiresAt } }
const adminSessions = new Map();

// Başarısız giriş sayacı: { ip: { count, bannedUntil } }
const loginAttempts  = new Map();

const SESSION_HOURS  = 8;
const MAX_ATTEMPTS   = 5;
const BAN_MINUTES    = 15;

function generateSession() {
  return crypto.randomBytes(48).toString('hex');
}

function isValidSession(req) {
  const token = req.cookies?.admin_session || req.headers['x-session'];
  if (!token) return false;
  const session = adminSessions.get(token);
  if (!session) return false;
  if (Date.now() > session.expiresAt) {
    adminSessions.delete(token);
    return false;
  }
  return true;
}

function checkBrute(ip) {
  const entry = loginAttempts.get(ip);
  if (!entry) return { blocked: false };
  if (entry.bannedUntil && Date.now() < entry.bannedUntil) {
    const mins = Math.ceil((entry.bannedUntil - Date.now()) / 60000);
    return { blocked: true, mins };
  }
  return { blocked: false };
}

function recordFail(ip) {
  const entry = loginAttempts.get(ip) || { count: 0 };
  entry.count++;
  if (entry.count >= MAX_ATTEMPTS) {
    entry.bannedUntil = Date.now() + BAN_MINUTES * 60 * 1000;
    entry.count = 0;
    console.log(\`[SECURITY] IP \${ip} banned for \${BAN_MINUTES} minutes\`);
  }
  loginAttempts.set(ip, entry);
}

function clearFail(ip) {
  loginAttempts.delete(ip);
}

// Cookie parser (basit)
app.use((req, res, next) => {
  req.cookies = {};
  const header = req.headers.cookie;
  if (header) {
    header.split(';').forEach(c => {
      const [k, v] = c.trim().split('=');
      if (k && v) req.cookies[k.trim()] = v.trim();
    });
  }
  next();
});

// ── POST /api/admin/login ─────────────────────────────────
app.post('/api/admin/login', (req, res) => {
  const ip = req.ip || req.connection.remoteAddress;

  // Ban kontrolü
  const brute = checkBrute(ip);
  if (brute.blocked) {
    return res.status(429).json({
      ok: false,
      error: \`Too many attempts. Try again in \${brute.mins} minutes.\`
    });
  }

  const { key } = req.body;

  // Şifre yanlış
  if (!key || key !== ADMIN_KEY) {
    recordFail(ip);
    // Sabit 1.2 sn bekle (timing attack önlemi)
    return setTimeout(() => {
      res.status(401).json({ ok: false, error: 'Wrong password' });
    }, 1200);
  }

  // Şifre doğru — session oluştur
  clearFail(ip);
  const token     = generateSession();
  const expiresAt = Date.now() + SESSION_HOURS * 3600 * 1000;
  adminSessions.set(token, { ip, expiresAt });

  // HttpOnly cookie — JS okuyamaz, XSS'e karşı koruma
  res.setHeader('Set-Cookie',
    \`admin_session=\${token}; HttpOnly; SameSite=Strict; Max-Age=\${SESSION_HOURS*3600}; Path=/\`
  );

  console.log(\`[ADMIN] Login from \${ip}\`);
  res.json({ ok: true });
});

// ── POST /api/admin/logout ────────────────────────────────
app.post('/api/admin/logout', (req, res) => {
  const token = req.cookies?.admin_session;
  if (token) adminSessions.delete(token);
  res.setHeader('Set-Cookie', 'admin_session=; Max-Age=0; Path=/');
  res.json({ ok: true });
});

// ── GET /admin — Admin paneli (session zorunlu) ───────────
// NOT: admin.html yerine /admin URL'si kullanılıyor
// Böylece admin.html dosyası hiç URL'de görünmüyor
app.get('/admin', (req, res) => {
  if (!isValidSession(req)) {
    return res.redirect('/admin-login');
  }
  res.sendFile(path.join(__dirname, '../admin.html')); // public dışında!
});

// ── GET /admin-login — Login sayfası ─────────────────────
app.get('/admin-login', (req, res) => {
  if (isValidSession(req)) return res.redirect('/admin');
  res.send(\`<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Admin Login</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{background:#030508;color:#e2e8f0;font-family:system-ui,sans-serif;
  display:flex;align-items:center;justify-content:center;min-height:100vh;}
.box{background:#0d1117;border:1px solid rgba(255,255,255,0.08);
  border-radius:14px;padding:2.5rem;width:360px;text-align:center;}
.logo{font-size:2.5rem;margin-bottom:1rem;}
h2{color:#f7c948;font-size:1.1rem;margin-bottom:.4rem;}
p{color:#64748b;font-size:.82rem;margin-bottom:1.8rem;}
input{width:100%;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);
  color:#e2e8f0;padding:.8rem 1rem;border-radius:8px;outline:none;
  font-size:.95rem;margin-bottom:1rem;letter-spacing:.1em;}
input:focus{border-color:rgba(247,201,72,.4);}
button{width:100%;background:#f7c948;color:#030508;border:none;
  padding:.85rem;border-radius:8px;cursor:pointer;font-weight:700;
  font-size:.95rem;transition:opacity .2s;}
button:hover{opacity:.85;}
.err{color:#ff6b6b;font-size:.82rem;margin-top:.8rem;display:none;}
.spin{display:none;}
</style></head>
<body><div class="box">
  <div class="logo">🔐</div>
  <h2>PUZZLE135 Admin</h2>
  <p>Authorized access only</p>
  <input type="password" id="pw" placeholder="••••••••••••"
    onkeydown="if(event.key==='Enter')login()">
  <button onclick="login()" id="btn">Login</button>
  <div class="err" id="err"></div>
</div>
<script>
async function login(){
  const pw=document.getElementById('pw').value;
  const btn=document.getElementById('btn');
  const err=document.getElementById('err');
  if(!pw)return;
  btn.textContent='...'; btn.disabled=true; err.style.display='none';
  try{
    const r=await fetch('/api/admin/login',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({key:pw})
    });
    const d=await r.json();
    if(d.ok){window.location.href='/admin';}
    else{err.textContent=d.error||'Wrong password';err.style.display='block';}
  }catch(e){err.textContent='Connection error';err.style.display='block';}
  btn.textContent='Login'; btn.disabled=false;
}
</script></body></html>\`);
});

// ── Admin API middleware — tüm /api/admin/* session ister ─
app.use('/api/admin', (req, res, next) => {
  // login endpoint'i hariç
  if (req.path === '/login') return next();
  if (!isValidSession(req)) {
    return res.status(401).json({ error: 'Not authenticated' });
  }
  next();
});

// ── Static dosyalar ──────────────────────────────────────
// admin.html burada YOK — server/ klasörünün yanında ayrı durur
app.use((req, res, next) => {
  // /admin.html veya admin içeren her isteği engelle
  if (req.path.toLowerCase().includes('admin')) {
    return res.redirect('/admin-login');
  }
  next();
});
app.use(express.static(path.join(__dirname, '../public'), {
  index: 'index.html'
}));

// ── ORTAM DEĞİŞKENLERİ ────────────────────────────────────
const PORT           = process.env.PORT           || 3000;
const CONTRACT_NAME  = process.env.CONTRACT_NAME  || 'puzzle135btc';
const ADMIN_ACCOUNT  = process.env.ADMIN_ACCOUNT  || 'puzzle135btc';
const ADMIN_KEY      = process.env.ADMIN_KEY      || 'changeme';      // Admin panel şifresi
const ADMIN_PRIVKEY  = process.env.ADMIN_PRIVATE_KEY;

// ── NFT EŞIĞI ─────────────────────────────────────────────
const NFT_THRESHOLD = 100;  // Her 100 Bkeys = 1 NFT
// Worker 150 Bkeys gönderir → 1 NFT mint, 50 Bkeys kalar
// Worker 50 Bkeys daha gönderir → toplamda 200 → 1 NFT daha mint

// ── WAX API ───────────────────────────────────────────────
const rpc = new JsonRpc('https://wax.greymass.com', { fetch });
const api = ADMIN_PRIVKEY ? new Api({
  rpc,
  signatureProvider: new JsSignatureProvider([ADMIN_PRIVKEY]),
  textDecoder: new TextDecoder(),
  textEncoder: new TextEncoder()
}) : null;

// ── VERİTABANI (SQLite — kalıcı) ──────────────────────────
const DB_PATH = path.join(__dirname, 'puzzle135.db');
const db      = new Database(DB_PATH);

// Tablo oluştur (yoksa)
db.exec(`
  CREATE TABLE IF NOT EXISTS contributors (
    wax_account   TEXT PRIMARY KEY,
    bkeys_total   INTEGER DEFAULT 0,   -- toplam Bkeys gönderilen
    nfts_minted   INTEGER DEFAULT 0,   -- toplam mint edilen NFT sayısı
    last_seen     INTEGER DEFAULT 0,   -- unix timestamp
    gpu_type      TEXT DEFAULT 'unknown'
  );

  CREATE TABLE IF NOT EXISTS pool (
    id            INTEGER PRIMARY KEY DEFAULT 0,
    total_bkeys   INTEGER DEFAULT 0,   -- tüm workerların toplamı
    total_nfts    INTEGER DEFAULT 0,   -- mint edilen toplam NFT
    solved        INTEGER DEFAULT 0,   -- 0=hayır, 1=evet
    started_at    INTEGER DEFAULT ${Date.now()}
  );

  CREATE TABLE IF NOT EXISTS mint_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    wax_account TEXT,
    bkeys_at    INTEGER,  -- kaçıncı Bkeys'de mint tetiklendi
    nfts        INTEGER,  -- kaç NFT mint edildi
    tx_id       TEXT,     -- WAX transaction ID
    minted_at   INTEGER DEFAULT ${Date.now()}
  );

  -- Pool kaydı yoksa oluştur
  INSERT OR IGNORE INTO pool (id) VALUES (0);
`);

// ── DB YARDIMCI FONKSİYONLARI ─────────────────────────────
const getContributor = db.prepare('SELECT * FROM contributors WHERE wax_account = ?');
const upsertContributor = db.prepare(`
  INSERT INTO contributors (wax_account, bkeys_total, nfts_minted, last_seen, gpu_type)
  VALUES (@wax_account, @bkeys_total, @nfts_minted, @last_seen, @gpu_type)
  ON CONFLICT(wax_account) DO UPDATE SET
    bkeys_total = @bkeys_total,
    nfts_minted = @nfts_minted,
    last_seen   = @last_seen,
    gpu_type    = @gpu_type
`);
const getPool    = db.prepare('SELECT * FROM pool WHERE id = 0');
const updatePool = db.prepare('UPDATE pool SET total_bkeys = ?, total_nfts = ? WHERE id = 0');
const insertLog  = db.prepare('INSERT INTO mint_log (wax_account, bkeys_at, nfts, tx_id, minted_at) VALUES (?, ?, ?, ?, ?)');

// ── AKTIF WORKER TRACKER (memory — sadece "son 5dk" için) ──
const workerHeartbeat = {}; // { wax_account: timestamp }

// ─────────────────────────────────────────────────────────
//  WAX SMART CONTRACT — NFT MINT
// ─────────────────────────────────────────────────────────
async function mintNFTsOnChain(waxAccount, nftCount, bkeys) {
  if (!api) {
    console.log(`[MINT-SIM] ${waxAccount} → ${nftCount} NFT (ADMIN_PRIVATE_KEY yok, simülasyon)`);
    return 'simulated-tx-' + Date.now();
  }

  // contract v2: mintnft(minter, to_account, bkeys, nfts_to_mint)
  // minter = ADMIN_ACCOUNT (addminter ile eklenmiş olmalı)
  try {
    const result = await api.transact({
      actions: [{
        account      : CONTRACT_NAME,
        name         : 'mintnft',
        authorization: [{ actor: ADMIN_ACCOUNT, permission: 'active' }],
        data: {
          minter       : ADMIN_ACCOUNT,
          to_account   : waxAccount,
          bkeys        : bkeys,          // bu rapordaki Bkeys
          nfts_to_mint : nftCount        // sunucunun hesapladığı NFT sayısı
        }
      }]
    }, { blocksBehind: 3, expireSeconds: 30 });

    const txId = result.transaction_id;
    console.log(`[MINT ✓] ${waxAccount} → ${nftCount} NFT | TX: ${txId}`);
    return txId;

  } catch (e) {
    console.error(`[MINT ERR] ${waxAccount}:`, e.message || e);
    throw e;
  }
}

// ─────────────────────────────────────────────────────────
//  POST /api/report
//
//  Worker her 30 saniyede bir buraya POST atar:
//  Body: { wax_account: "myacc.wax", bkeys: 450, gpu_type: "cuda" }
//
//  Sunucu:
//  1. Kişinin birikimli Bkeys sayısını artırır
//  2. Her 100 Bkeys geçişinde 1 NFT mint tetikler
//  3. Mint sonucunu loglar
// ─────────────────────────────────────────────────────────
app.post('/api/report', async (req, res) => {
  const { wax_account, bkeys, gpu_type = 'unknown' } = req.body;

  // ── Validasyon ──────────────────────────────────────────
  if (!wax_account || typeof wax_account !== 'string') {
    return res.status(400).json({ error: 'wax_account required' });
  }
  if (!bkeys || typeof bkeys !== 'number' || bkeys <= 0) {
    return res.status(400).json({ error: 'bkeys must be a positive number' });
  }
  if (bkeys > 50_000) {
    return res.status(400).json({ error: 'bkeys too large — max 50,000 per report' });
  }

  // ── Heartbeat ───────────────────────────────────────────
  workerHeartbeat[wax_account] = Date.now();

  // ── DB'den mevcut durumu al ──────────────────────────────
  let contributor = getContributor.get(wax_account);

  const prev_bkeys  = contributor ? contributor.bkeys_total  : 0;
  const prev_minted = contributor ? contributor.nfts_minted  : 0;

  // ── YENİ BİRİKİMLİ BKEYS ────────────────────────────────
  const new_bkeys_total = prev_bkeys + bkeys;

  // ── KAÇ NFT MİNT EDİLECEK? ──────────────────────────────
  //
  //  Örnek:
  //  prev_bkeys = 50  →  prev_minted = 0   (50 < 100, henüz mint yok)
  //  yeni bkeys = 70  →  new_bkeys_total = 120
  //  new_should_mint = floor(120 / 100) = 1
  //  nfts_to_mint    = 1 - 0 = 1  →  ✅ 1 NFT mint!
  //
  //  Bir sonraki rapor:
  //  prev_bkeys = 120, prev_minted = 1
  //  yeni bkeys = 40  →  new_bkeys_total = 160
  //  new_should_mint = floor(160 / 100) = 1
  //  nfts_to_mint    = 1 - 1 = 0  →  ❌ henüz değil (160 < 200)
  //
  //  Sonraki rapor:
  //  prev_bkeys = 160, prev_minted = 1
  //  yeni bkeys = 80  →  new_bkeys_total = 240
  //  new_should_mint = floor(240 / 100) = 2
  //  nfts_to_mint    = 2 - 1 = 1  →  ✅ 1 NFT daha mint!

  const new_should_mint = Math.floor(new_bkeys_total / NFT_THRESHOLD);
  const nfts_to_mint    = new_should_mint - prev_minted;
  const new_minted      = prev_minted + nfts_to_mint;

  // ── DB KAYDET ────────────────────────────────────────────
  upsertContributor.run({
    wax_account,
    bkeys_total : new_bkeys_total,
    nfts_minted : new_minted,
    last_seen   : Date.now(),
    gpu_type
  });

  const pool = getPool.get();
  updatePool.run(pool.total_bkeys + bkeys, pool.total_nfts + nfts_to_mint);

  // ── NFT MINT (eğer eşik aşıldıysa) ──────────────────────
  let tx_id = null;
  if (nfts_to_mint > 0) {
    console.log(`[NFT] ${wax_account}: ${prev_bkeys} → ${new_bkeys_total} Bkeys | ${nfts_to_mint} NFT mint ediliyor...`);
    try {
      tx_id = await mintNFTsOnChain(wax_account, nfts_to_mint, new_bkeys_total);
      insertLog.run(wax_account, new_bkeys_total, nfts_to_mint, tx_id, Date.now());
    } catch (e) {
      // Mint başarısız → DB'de mint sayısını geri al (tekrar denenir)
      upsertContributor.run({
        wax_account,
        bkeys_total : new_bkeys_total,
        nfts_minted : prev_minted,   // geri al!
        last_seen   : Date.now(),
        gpu_type
      });
      return res.status(500).json({ error: 'NFT mint failed', details: e.message });
    }
  }

  // ── YANIT ────────────────────────────────────────────────
  const updatedPool = getPool.get();
  return res.json({
    ok              : true,
    wax_account,
    bkeys_this_report   : bkeys,
    bkeys_total         : new_bkeys_total,
    bkeys_until_next_nft: NFT_THRESHOLD - (new_bkeys_total % NFT_THRESHOLD),
    new_nfts_minted : nfts_to_mint,
    user_total_nfts : new_minted,
    tx_id,
    pool: {
      total_bkeys : updatedPool.total_bkeys,
      total_nfts  : updatedPool.total_nfts
    }
  });
});

// ─────────────────────────────────────────────────────────
//  GET /api/stats — Public
// ─────────────────────────────────────────────────────────
app.get('/api/stats', (req, res) => {
  const pool    = getPool.get();
  const now     = Date.now();
  const cutoff  = now - 5 * 60 * 1000; // son 5 dk

  const active_workers = Object.values(workerHeartbeat)
    .filter(ts => ts > cutoff).length;

  // Pool solved bilgisi gizli (admin'e özel)
  res.json({
    total_nfts     : pool.total_nfts,
    total_bkeys    : pool.total_bkeys,
    active_workers,
    nft_threshold  : NFT_THRESHOLD,
    solved         : pool.solved === 1   // sadece bool, key değil
  });
});

// ─────────────────────────────────────────────────────────
//  GET /api/leaderboard — Top 50
// ─────────────────────────────────────────────────────────
app.get('/api/leaderboard', (req, res) => {
  const pool  = getPool.get();
  const total = pool.total_nfts || 1;

  const rows = db.prepare(`
    SELECT wax_account, nfts_minted as nft_count, bkeys_total, gpu_type
    FROM contributors
    ORDER BY nfts_minted DESC
    LIMIT 50
  `).all();

  const lb = rows.map((r, i) => ({
    rank       : i + 1,
    account    : r.wax_account,
    nft_count  : r.nft_count,
    bkeys_total: r.bkeys_total,
    gpu_type   : r.gpu_type,
    share_pct  : ((r.nft_count / total) * 100).toFixed(4)
  }));

  res.json(lb);
});

// ─────────────────────────────────────────────────────────
//  GET /api/user/:account
// ─────────────────────────────────────────────────────────
app.get('/api/user/:account', (req, res) => {
  const pool  = getPool.get();
  const total = pool.total_nfts || 1;
  const user  = getContributor.get(req.params.account);

  if (!user) return res.json({ nft_count: 0, bkeys_total: 0, share_pct: '0' });

  res.json({
    wax_account  : user.wax_account,
    nft_count    : user.nfts_minted,
    bkeys_total  : user.bkeys_total,
    bkeys_until_next_nft: NFT_THRESHOLD - (user.bkeys_total % NFT_THRESHOLD),
    gpu_type     : user.gpu_type,
    share_pct    : ((user.nfts_minted / total) * 100).toFixed(4),
    last_seen    : user.last_seen
  });
});

// ─────────────────────────────────────────────────────────
//  POST /api/admin/login — Şifre kontrol et
// ─────────────────────────────────────────────────────────
app.post('/api/admin/login', (req, res) => {
  const { key } = req.body;
  if (!key || key !== ADMIN_KEY) {
    // Brute force koruma: 1 saniye beklet
    return setTimeout(() => {
      res.status(401).json({ ok: false, error: 'Wrong password' });
    }, 1000);
  }
  res.json({ ok: true });
});

// ─────────────────────────────────────────────────────────
//  GET /api/admin/stats — Admin Only
//  Header: X-Admin-Key: <ADMIN_KEY>
// ─────────────────────────────────────────────────────────
app.get('/api/admin/stats', (req, res) => {
  if (req.headers['x-admin-key'] !== ADMIN_KEY) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  const pool = getPool.get();
  const top  = db.prepare('SELECT * FROM contributors ORDER BY nfts_minted DESC LIMIT 100').all();
  const logs = db.prepare('SELECT * FROM mint_log ORDER BY id DESC LIMIT 50').all();

  res.json({
    pool,
    top_contributors: top,
    recent_mints    : logs,
    uptime_ms       : Date.now() - pool.started_at
  });
});

// ─────────────────────────────────────────────────────────
//  POST /api/solved — Worker puzzle çözdüğünde bildirir
// ─────────────────────────────────────────────────────────
app.post('/api/solved', (req, res) => {
  const { wax_account, line, admin_secret } = req.body;
  console.log('\n🎉 PUZZLE ÇÖZÜM BİLDİRİMİ:', { wax_account, line });

  // Admin KEY ile işaretlenebilir
  if (admin_secret === ADMIN_KEY) {
    db.prepare('UPDATE pool SET solved = 1 WHERE id = 0').run();
    console.log('✅ Pool solved=1 işaretlendi');
  }

  res.json({ ok: true });
});

// ─────────────────────────────────────────────────────────
//  GET /api/download/worker — Worker indir
// ─────────────────────────────────────────────────────────
const { workerDownloadHandler } = require('../workers/builder');
app.get('/api/download/worker', workerDownloadHandler);

// ─────────────────────────────────────────────────────────
//  SUNUCU BAŞLAT
// ─────────────────────────────────────────────────────────
app.listen(PORT, () => {
  const pool = getPool.get();
  console.log(`
╔══════════════════════════════════════════════════════╗
║         PUZZLE135 Pool Server — Başladı             ║
╠══════════════════════════════════════════════════════╣
║  Port       : ${PORT}                                  
║  Contract   : ${CONTRACT_NAME}                        
║  Admin      : ${ADMIN_ACCOUNT}                       
║  NFT Eşiği : Her ${NFT_THRESHOLD} Bkeys = 1 NFT     
║  DB         : ${DB_PATH}                             
╠══════════════════════════════════════════════════════╣
║  Total NFTs : ${pool.total_nfts}                     
║  Total Bkeys: ${pool.total_bkeys}                    
╚══════════════════════════════════════════════════════╝
  `);
});
