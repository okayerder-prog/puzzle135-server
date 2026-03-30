// ============================================================
// PUZZLE135 Worker Builder
// WAX hesabını Python script'e inject eder ve .exe olarak sunar
// Node.js Express endpoint — server/index.js içine ekle
// ============================================================

const fs   = require('fs');
const path = require('path');
const { exec } = require('child_process');

const WORKER_SRC_DIR = path.join(__dirname, '../workers/src');
const WORKER_OUT_DIR = path.join(__dirname, '../workers/dist');
const POOL_URL       = process.env.POOL_URL || 'http://localhost:3000';

// dist klasörü yoksa oluştur
if (!fs.existsSync(WORKER_OUT_DIR)) fs.mkdirSync(WORKER_OUT_DIR, { recursive: true });

/**
 * WAX hesabını ve pool URL'yi Python script'e inject eder
 * Sonra PyInstaller ile .exe'ye derler
 */
async function buildWorker(waxAccount, gpuType) {
  return new Promise((resolve, reject) => {
    const srcFile  = gpuType === 'cuda' ? 'cuda_worker.py'   : 'vulkan_worker.py';
    const outName  = gpuType === 'cuda' ? 'puzzle135-cuda-worker' : 'puzzle135-vulkan-worker';
    const tmpFile  = path.join(WORKER_OUT_DIR, `${outName}_${waxAccount.replace(/\./g,'_')}.py`);
    const exeFile  = path.join(WORKER_OUT_DIR, `${outName}.exe`);

    // 1. Kaynak dosyayı oku
    let src = fs.readFileSync(path.join(WORKER_SRC_DIR, srcFile), 'utf8');

    // 2. Placeholder'ları gerçek değerlerle değiştir
    src = src
      .replace('__WAX_ACCOUNT__', waxAccount)
      .replace('__POOL_URL__',    POOL_URL);

    // 3. Inject edilmiş Python dosyasını yaz
    fs.writeFileSync(tmpFile, src, 'utf8');

    // 4. PyInstaller ile .exe'ye derle
    const cmd = [
      'pyinstaller',
      '--onefile',
      '--clean',
      '--noconfirm',
      `--name=${outName}`,
      `--distpath=${WORKER_OUT_DIR}`,
      `--workpath=${path.join(WORKER_OUT_DIR, 'build')}`,
      `--specpath=${path.join(WORKER_OUT_DIR, 'specs')}`,
      `"${tmpFile}"`
    ].join(' ');

    console.log(`[BUILD] ${waxAccount} için ${gpuType} worker derleniyor...`);
    exec(cmd, { timeout: 120000 }, (err, stdout, stderr) => {
      // Temp py dosyasını sil
      try { fs.unlinkSync(tmpFile); } catch {}

      if (err) {
        console.error('[BUILD HATA]', err.message);
        reject(err);
        return;
      }
      console.log(`[BUILD ✓] ${exeFile} hazır`);
      resolve(exeFile);
    });
  });
}

/**
 * Express endpoint — /api/download/worker
 * ?wax=myaccount.wax&type=cuda|vulkan
 */
async function workerDownloadHandler(req, res) {
  const { wax, type } = req.query;

  if (!wax) return res.status(400).json({ error: 'WAX hesabı gerekli' });

  const gpuType  = type === 'cuda' ? 'cuda' : 'vulkan';
  const fileName = gpuType === 'cuda'
    ? 'puzzle135-cuda-worker.exe'
    : 'puzzle135-vulkan-worker.exe';

  const exePath = path.join(WORKER_OUT_DIR, fileName);

  // Önce cache'de var mı kontrol et
  // Gerçek projede her kullanıcı için ayrı build yapılmaz,
  // bunun yerine config dosyası inject edilir (daha hızlı)
  if (fs.existsSync(exePath)) {
    console.log(`[DOWNLOAD] ${wax} → ${gpuType} (cache'den)`);
    res.setHeader('Content-Disposition', `attachment; filename="${fileName}"`);
    res.setHeader('Content-Type', 'application/octet-stream');
    // Config bilgisini header'a ekle (worker startup'ta okur)
    res.setHeader('X-Pool-Url',     POOL_URL);
    res.setHeader('X-Wax-Account',  wax);
    return fs.createReadStream(exePath).pipe(res);
  }

  // Cache yoksa derle
  try {
    const built = await buildWorker(wax, gpuType);
    res.setHeader('Content-Disposition', `attachment; filename="${fileName}"`);
    res.setHeader('Content-Type', 'application/octet-stream');
    res.setHeader('X-Pool-Url',    POOL_URL);
    res.setHeader('X-Wax-Account', wax);
    fs.createReadStream(built).pipe(res);
  } catch (e) {
    // Derleme başarısız → Python script olarak sun
    const srcFile = gpuType === 'cuda' ? 'cuda_worker.py' : 'vulkan_worker.py';
    let src = fs.readFileSync(path.join(WORKER_SRC_DIR, srcFile), 'utf8');
    src = src.replace('__WAX_ACCOUNT__', wax).replace('__POOL_URL__', POOL_URL);

    const pyName = fileName.replace('.exe', '.py');
    res.setHeader('Content-Disposition', `attachment; filename="${pyName}"`);
    res.setHeader('Content-Type', 'text/plain');
    res.send(src);
  }
}

module.exports = { workerDownloadHandler, buildWorker };
