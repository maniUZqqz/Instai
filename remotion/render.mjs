// Renders one InstAI composition to a video (or a still). Started by InstAI's `remotion.render` job:  node render.mjs <job.json>
//   job.json: { composition, props, out, still?: <frame>, browser?: "<chrome/edge/headless-shell path>", chrome_mode?: "headless-shell"|"chrome-for-testing",
//               crf?: 18, concurrency?: <n>, hw_accel?: true, scale?: <0.25..2: the video / still is rendered at this scale of the composition's size>,
//               bundle_dir?: "<folder to keep the bundle in>",
//               qa?: { items: [{ name, composition, props, frames: [{ name, frame }] }], out_dir, scale?: 0.5, quality?: 88, offline?: true } }
//   with `qa` the script renders those frames as JPEG pictures and collects, per frame, the geometry every text block reports on the console («INSTAI_QA:{json}», see
//   src/components/qa.tsx); the answer is <out_dir>/results.json = [{ name, composition, width, height, fps, frames, shots: [{ name, frame, image, geometry }] }]
//   node render.mjs --probe     prints what is installed (versions, browser) as one JSON line
// Every line this script prints that starts with "INSTAI_REMOTION " is a JSON event (bundle / render progress, done, error); the rest is a log.
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const emit = (o) => process.stdout.write('INSTAI_REMOTION ' + JSON.stringify(o) + '\n')

function walk(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) walk(p, out)
    else out.push(p)
  }
  return out.sort()
}

/** A hash of everything that decides what the bundle contains: the sources, the public files and the package versions. */
function sourceHash() {
  const h = crypto.createHash('sha256')
  for (const f of [...walk(path.join(HERE, 'src')), ...walk(path.join(HERE, 'public')), path.join(HERE, 'package.json')]) {
    h.update(path.relative(HERE, f).replace(/\\/g, '/'))
    h.update(fs.readFileSync(f))
  }
  return h.digest('hex').slice(0, 16)
}

async function probe() {
  const out = { node: process.version, platform: process.platform }
  try {
    const r = await import('@remotion/renderer')
    out.renderer = true
    out.remotion = JSON.parse(fs.readFileSync(path.join(HERE, 'node_modules', 'remotion', 'package.json'), 'utf8')).version
    out.chrome_default = r.BrowserSafeApis ? true : undefined
  } catch (e) {
    out.renderer = false
    out.error = String(e && e.message ? e.message : e).slice(0, 300)
  }
  emit({ event: 'probe', ...out })
}

/** QA mode: pictures of chosen frames + the geometry of every text block, for one or many compositions with ONE browser (the render of a shot, the self-test of every component). */
async function runQa(job, serveUrl) {
  const { openBrowser, renderStill, selectComposition } = await import('@remotion/renderer')
  const q = job.qa
  const flags = { 'disable-background-networking': true }
  if (q.offline !== false) flags['host-resolver-rules'] = 'MAP * ~NOTFOUND , EXCLUDE localhost , EXCLUDE 127.0.0.1'
  const chromiumOptions = { gl: job.gl === undefined ? 'swangle' : job.gl, flags }
  emit({ event: 'phase', phase: 'preparing' })
  const instance = await openBrowser('chrome', { browserExecutable: job.browser || null, chromeMode: job.chrome_mode || undefined, chromiumOptions, logLevel: 'error' })
  const results = []
  try {
    fs.mkdirSync(q.out_dir, { recursive: true })
    const total = q.items.reduce((n, it) => n + it.frames.length, 0)
    let done = 0
    for (const item of q.items) {
      const props = JSON.parse(JSON.stringify(item.props || {}))
      if (props.spec) props.spec.qa = true
      const composition = await selectComposition({ serveUrl, id: item.composition, inputProps: props, puppeteerInstance: instance, chromiumOptions, logLevel: 'error', timeoutInMilliseconds: Number(q.timeout_ms) || 90000 })
      const shots = []
      for (const f of item.frames) {
        const logs = []
        const out = path.join(q.out_dir, `${f.name}.jpg`)
        await renderStill({
          composition, serveUrl, inputProps: props, output: out, frame: Math.max(0, Math.min(Number(f.frame) || 0, composition.durationInFrames - 1)),
          scale: Number(q.scale) || 0.5, imageFormat: 'jpeg', jpegQuality: Number(q.quality) || 88, puppeteerInstance: instance, chromiumOptions, logLevel: 'error',
          timeoutInMilliseconds: Number(q.timeout_ms) || 90000,
          onBrowserLog: (l) => {
            const t = String((l && l.text) || '')
            if (t.startsWith('INSTAI_QA:')) logs.push(t.slice(10))
          },
        })
        let geometry = null
        for (let i = logs.length - 1; i >= 0 && !geometry; i--) {
          try {
            geometry = JSON.parse(logs[i])
          } catch (e) {
            /* the next line */
          }
        }
        shots.push({ name: f.name, frame: f.frame, image: out, geometry })
        done += 1
        emit({ event: 'qa_progress', done, total })
      }
      results.push({ name: item.name, composition: item.composition, width: composition.width, height: composition.height, fps: composition.fps, frames: composition.durationInFrames, shots })
    }
  } finally {
    try {
      await instance.close({ silent: true })
    } catch (e) {
      /* ignore */
    }
  }
  fs.writeFileSync(path.join(q.out_dir, 'results.json'), JSON.stringify(results))
}

async function main() {
  if (process.argv[2] === '--probe') return probe()
  const job = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'))
  const { bundle } = await import('@remotion/bundler')
  const { renderMedia, renderStill, selectComposition } = await import('@remotion/renderer')
  const t0 = Date.now()

  // 1. the bundle (cached per source hash; rebuilt only when a source or a package version changed)
  const hash = sourceHash()
  const root = job.bundle_dir || path.join(HERE, '.cache')
  const serveUrl = path.join(root, 'bundle-' + hash)
  if (!fs.existsSync(path.join(serveUrl, 'index.html'))) {
    emit({ event: 'phase', phase: 'bundling' })
    fs.mkdirSync(root, { recursive: true })
    let last = 0
    await bundle({
      entryPoint: path.join(HERE, 'src', 'index.ts'),
      publicDir: path.join(HERE, 'public'),
      outDir: serveUrl,
      onProgress: (p) => {
        if (p - last >= 5 || p === 100) {
          last = p
          emit({ event: 'bundle', progress: p })
        }
      },
    })
    for (const old of fs.readdirSync(root)) {
      if (old.startsWith('bundle-') && old !== 'bundle-' + hash) fs.rmSync(path.join(root, old), { recursive: true, force: true })
    }
  } else {
    emit({ event: 'bundle', progress: 100, cached: true })
  }

  if (job.qa) {
    await runQa(job, serveUrl)
    emit({ event: 'done', qa: true, out: path.join(job.qa.out_dir, 'results.json'), seconds: (Date.now() - t0) / 1000 })
    return
  }

  // 2. the browser: the one InstAI found on this PC (Chrome / Edge / a headless shell); never a download
  const common = {
    serveUrl,
    inputProps: job.props || {},
    logLevel: 'warn',
    ...(job.browser ? { browserExecutable: job.browser } : {}),
    ...(job.chrome_mode ? { chromeMode: job.chrome_mode } : {}),
    chromiumOptions: { ...(job.gl ? { gl: job.gl } : {}) },
  }
  emit({ event: 'phase', phase: 'preparing' })
  const composition = await selectComposition({ ...common, id: job.composition })
  emit({ event: 'composition', id: composition.id, width: composition.width, height: composition.height, fps: composition.fps, frames: composition.durationInFrames })

  fs.mkdirSync(path.dirname(job.out), { recursive: true })
  if (job.still !== undefined && job.still !== null) {
    emit({ event: 'phase', phase: 'rendering' })
    await renderStill({ ...common, composition, output: job.out, frame: Math.max(0, Math.min(composition.durationInFrames - 1, Number(job.still) || 0)), imageFormat: 'png', ...(job.scale ? { scale: Number(job.scale) } : {}) })
    emit({ event: 'done', out: job.out, still: true, width: composition.width, height: composition.height, seconds: (Date.now() - t0) / 1000 })
    return
  }

  // 3. the video
  emit({ event: 'phase', phase: 'rendering' })
  let lastTick = 0
  await renderMedia({
    ...common,
    composition,
    codec: 'h264',
    crf: job.crf ?? 18,
    pixelFormat: 'yuv420p',
    outputLocation: job.out,
    overwrite: true,
    ...(job.concurrency ? { concurrency: job.concurrency } : {}),
    ...(job.scale ? { scale: Number(job.scale) } : {}),
    ...(job.hw_accel ? { hardwareAcceleration: 'if-possible' } : {}),
    onProgress: ({ renderedFrames, encodedFrames, progress }) => {
      const now = Date.now()
      if (now - lastTick > 500 || progress >= 1) {
        lastTick = now
        emit({ event: 'progress', rendered: renderedFrames, encoded: encodedFrames, frames: composition.durationInFrames, progress })
      }
    },
  })
  emit({ event: 'done', out: job.out, width: composition.width, height: composition.height, fps: composition.fps, frames: composition.durationInFrames, seconds: (Date.now() - t0) / 1000 })
}

main().then(
  () => process.exit(0),
  (e) => {
    emit({ event: 'error', message: String(e && e.message ? e.message : e).slice(0, 1500), stack: String(e && e.stack ? e.stack : '').slice(0, 1200) })
    process.exit(1)
  },
)
