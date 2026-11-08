/* Supplemental protocol experiments in an isolated headless Chromium.
 * Uses a system-installed puppeteer-core; no FORGE services or learner data.
 * FORGE_PUPPETEER_MODULE=/path/to/puppeteer-core node api/tools/p5_browser_checks.cjs /path/to/chromium
 */
const assert = require('node:assert/strict');
const http = require('node:http');
const puppeteer = require(process.env.FORGE_PUPPETEER_MODULE || 'puppeteer-core');

(async () => {
  const counts = { simple: 0, preflight: 0, json: 0, cache: 0, conditional: 0 };
  let callerOrigin;
  const api = http.createServer((req, res) => {
    if (req.url === '/cookie') {
      res.setHeader('Set-Cookie', 'p5=lax; SameSite=Lax; Path=/');
      return res.end('set');
    }
    if (req.url === '/echo-cookie') {
      if (req.method === 'POST') counts.cross_site_post_cookie = req.headers.cookie || 'none';
      return res.end(req.headers.cookie || 'none');
    }
    if (req.url === '/cache') {
      counts.cache++;
      res.setHeader('Cache-Control', 'public, max-age=120');
      res.setHeader('ETag', '"p5-v1"');
      if (req.headers['if-none-match'] === '"p5-v1"') {
        counts.conditional++;
        res.statusCode = 304;
        return res.end();
      }
      return res.end('cache-body');
    }
    const allowed = req.url === '/allowed';
    if (allowed) {
      res.setHeader('Access-Control-Allow-Origin', callerOrigin);
      res.setHeader('Access-Control-Allow-Credentials', 'true');
      res.setHeader('Vary', 'Origin');
    }
    if (req.url === '/wildcard') {
      res.setHeader('Access-Control-Allow-Origin', '*');
      res.setHeader('Access-Control-Allow-Credentials', 'true');
    }
    if (req.method === 'OPTIONS') {
      counts.preflight++;
      if (allowed) {
        res.setHeader('Access-Control-Allow-Methods', 'POST');
        res.setHeader('Access-Control-Allow-Headers', 'content-type,x-csrf-token');
      }
      return res.end();
    }
    if (req.method === 'POST') {
      if (req.headers['content-type']?.includes('application/json')) counts.json++;
      else counts.simple++;
    }
    res.end('response');
  });
  const caller = http.createServer((req, res) => res.end('<!doctype html><title>P5 protocol test</title>'));
  let browser;
  try {
    await new Promise(resolve => api.listen(0, '127.0.0.1', resolve));
    await new Promise(resolve => caller.listen(0, '127.0.0.1', resolve));
    const apiOrigin = `http://127.0.0.1:${api.address().port}`;
    callerOrigin = `http://127.0.0.1:${caller.address().port}`;
    browser = await puppeteer.launch({ executablePath: process.argv[2], headless: true });
    const page = await browser.newPage();
    await page.goto(callerOrigin);
    const fetchResult = (path, options) => page.evaluate(async (url, init) => {
      try { return { readable: true, text: await (await fetch(url, init)).text() }; }
      catch { return { readable: false }; }
    }, apiOrigin + path, options);
    assert.deepEqual(await fetchResult('/denied', { method: 'POST', body: 'simple' }), { readable: false });
    assert.equal(counts.simple, 1); // Sent, response unreadable.
    assert.deepEqual(await fetchResult('/denied', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'test' }, body: '{}' }), { readable: false });
    assert.equal(counts.preflight, 1);
    assert.equal(counts.json, 0); // Denied preflight blocked the actual JSON POST.
    assert.equal((await fetchResult('/allowed', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'test' }, body: '{}' })).readable, true);
    assert.equal(counts.json, 1);
    assert.equal((await fetchResult('/wildcard', { credentials: 'include' })).readable, false);
    await page.goto(apiOrigin + '/cookie');
    // localhost and 127.0.0.1 are distinct sites; different ports alone are not.
    await page.goto(callerOrigin.replace('127.0.0.1', 'localhost'));
    const cookieEcho = await fetchResult('/echo-cookie', { method: 'POST', credentials: 'include' });
    assert.equal(cookieEcho.readable, false); // CORS still restricts the script.
    assert.equal(counts.cross_site_post_cookie, 'none');
    // Top-level navigation GET can send an explicit Lax cookie cross-site.
    await page.goto(apiOrigin + '/echo-cookie');
    assert.match(await page.evaluate(() => document.body.textContent), /p5=lax/);
    await page.goto(apiOrigin + '/');
    const cache = await page.evaluate(async () => {
      const first = await (await fetch('/cache')).text();
      const second = await (await fetch('/cache')).text();
      const validated = await (await fetch('/cache', { cache: 'no-cache' })).text();
      return { first, second, validated };
    });
    assert.deepEqual(cache, { first: 'cache-body', second: 'cache-body', validated: 'cache-body' });
    assert.equal(counts.cache, 2); // Second fetch reused a fresh browser cache entry.
    assert.equal(counts.conditional, 1); // Forced validation used ETag and a 304.
    console.log(JSON.stringify({ browser: await browser.version(), counts, passed: true }));
  } finally {
    if (browser) await browser.close();
    await Promise.all([new Promise(resolve => api.close(resolve)), new Promise(resolve => caller.close(resolve))]);
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
