/* Actual React examples in isolated headless Chromium; no app or learner data.
 * FORGE_PUPPETEER_MODULE=/path/to/puppeteer-core node api/tools/validate_p6_browser.cjs /path/to/chromium
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const puppeteer = require(process.env.FORGE_PUPPETEER_MODULE || 'puppeteer-core');
const root = path.resolve(__dirname, '../..');
const ts = require(path.join(root, 'web/node_modules/typescript'));
const moduleFiles = {
  react: 'react/cjs/react.development.js',
  'react-dom': 'react-dom/cjs/react-dom.development.js',
  'react-dom/client': 'react-dom/cjs/react-dom-client.development.js',
  scheduler: 'scheduler/cjs/scheduler.development.js',
};
const factories = Object.entries(moduleFiles).map(([name,file]) =>
  `${JSON.stringify(name)}:function(module,exports,require){${fs.readFileSync(path.join(root,'web/node_modules',file),'utf8')}\n}`);
const files = fs.readdirSync(path.join(root,'api/app/seed/lessons'));
const sources = {};
for (const file of files.filter(file => /^(26|27)-/.test(file))) {
  const body = fs.readFileSync(path.join(root,'api/app/seed/lessons',file),'utf8');
  const slug = body.match(/^slug = "([^"]+)"/m)[1];
  sources[slug] = body.match(/^```jsx\n([\s\S]*?)^```/m)[1];
}
const listSlug = 'react-list-identity-and-derived-data';
const effectSlug = 'react-effects-and-request-lifetimes';

function bundle(slug, variant) {
  let source = sources[slug];
  assert(source, 'Unknown lesson');
  if (variant === 'index') {
    const original = 'visible.map(task => <Row key={task.id} task={task} />)';
    assert(source.includes(original));
    source = source.replace(original, 'visible.map((task, index) => <Row key={index} task={task} />)');
  }
  if (variant === 'controlled' || variant === 'strict') {
    const start = source.indexOf('function lookup(query) {');
    const end = source.indexOf('\n\nfunction Search()',start);
    assert(start >= 0 && end > start);
    source = source.slice(0,start) + `window.p6Pending=[]; window.p6Publications=[];
function lookup(query) { return new Promise((resolve,reject) => window.p6Pending.push({query,resolve,reject})); }
` + source.slice(end);
    source = source.replace('if (!ignore) setResult({ query, items, error: null });',
      'if (!ignore) { window.p6Publications.push(query); setResult({ query, items, error: null }); }');
    source = source.replace('if (!ignore) setResult({ query, items: [], error: error.message });',
      'if (!ignore) { window.p6Publications.push(query); setResult({ query, items: [], error: error.message }); }');
    source = source.replace('createRoot(document.getElementById("root")).render(',
      'const lessonRoot=createRoot(document.getElementById("root")); window.p6Unmount=()=>lessonRoot.unmount(); lessonRoot.render(');
    if (variant === 'strict') source = source.replace('const [query, setQuery] = useState("");','const [query, setQuery] = useState("strict");');
  }
  const emitted = ts.transpileModule(source, { compilerOptions: {
    jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.CommonJS, esModuleInterop: true,
  }, reportDiagnostics: true });
  assert.equal((emitted.diagnostics || []).filter(d=>d.category===ts.DiagnosticCategory.Error).length,0);
  return `(function(){const process={env:{NODE_ENV:'development'}}; const cache={};
const factories={${factories.join(',')},entry:function(module,exports,require){${emitted.outputText}\n}};
function require(name){if(cache[name])return cache[name].exports; const module={exports:{}};cache[name]=module;
if(!factories[name])throw new Error('Unknown module '+name);factories[name](module,module.exports,require);return module.exports;} require('entry');})();`;
}

(async () => {
  const server = http.createServer((req,res) => {
    const url = new URL(req.url,'http://fixture');
    if (url.pathname === '/bundle.js') {
      res.setHeader('Content-Type','text/javascript');
      return res.end(bundle(url.searchParams.get('slug'),url.searchParams.get('variant')));
    }
    res.setHeader('Content-Type','text/html');
    res.end(`<!doctype html><div id="root"></div><script src="/bundle.js${url.search}"></script>`);
  });
  let browser;
  const errors=[];
  const results=[];
  try {
    await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
    const origin=`http://127.0.0.1:${server.address().port}`;
    browser=await puppeteer.launch({executablePath:process.argv[2],headless:true});
    async function pageFor(slug,variant='original') {
      const page=await browser.newPage();
      page.on('pageerror',error=>errors.push(String(error)));
      await page.setRequestInterception(true);
      page.on('request',request=>request.url().startsWith(origin)?request.continue():request.abort());
      await page.goto(`${origin}/?slug=${slug}&variant=${variant}`);
      await page.waitForSelector('input');
      return page;
    }
    async function value(page, selector, text) {
      await page.evaluate((selector,text)=>{
        const input=document.querySelector(selector);
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,text);
        input.dispatchEvent(new Event('input',{bubbles:true}));
      },selector,text);
    }
    const drafts=page=>page.$$eval('li',rows=>rows.map(row=>({id:row.dataset.task,value:row.querySelector('input').value})));
    for (const variant of ['original','index']) {
      const page=await pageFor(listSlug,variant);
      await value(page,'[aria-label="Draft for a1"]','Asha note');
      await page.click('button');
      await page.waitForFunction(()=>document.querySelector('li').dataset.task==='b2');
      const after=await drafts(page);
      assert.deepEqual(after,variant==='original'?[{id:'b2',value:'Bo'},{id:'a1',value:'Asha note'}]:[{id:'b2',value:'Asha note'},{id:'a1',value:'Bo'}]);
      if (variant==='original') {
        await value(page,'[aria-label="Filter"]','Bo');
        await page.waitForFunction(()=>document.querySelectorAll('li').length===1);
        await value(page,'[aria-label="Filter"]','');
        await page.waitForFunction(()=>document.querySelectorAll('li').length===2);
        assert.equal((await drafts(page)).find(row=>row.id==='a1').value,'Asha');
      }
      results.push({lesson:listSlug,variant,after_reverse:after,passed:true});
      await page.close();
    }
    const original=await pageFor(effectSlug);
    const expectOutput=(page,text)=>page.waitForFunction(text=>document.querySelector('output').textContent===text,{},text);
    await expectOutput(original,'Enter a query');
    for (const [query,output] of [['slow','Result for slow'],['fast','Result for fast'],['fail','Lookup failed'],['','Enter a query']]) {
      await value(original,'[aria-label="Query"]',query);
      await expectOutput(original,output);
    }
    results.push({lesson:effectSlug,variant:'original timers',passed:true});
    await original.close();
    const page=await pageFor(effectSlug,'controlled');
    async function pending(query) {
      await value(page,'[aria-label="Query"]',query);
      await page.waitForFunction(query=>window.p6Pending.some(entry=>entry.query===query),{},query);
    }
    await pending('slow');await pending('fast');
    await page.evaluate(()=>window.p6Pending.find(entry=>entry.query==='fast').resolve(['Result for fast']));
    await expectOutput(page,'Result for fast');
    await page.evaluate(()=>window.p6Pending.find(entry=>entry.query==='slow').resolve(['Result for slow']));
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    await expectOutput(page,'Result for fast');
    await pending('fail');
    await page.evaluate(()=>window.p6Pending.find(entry=>entry.query==='fail').reject(new Error('Lookup failed')));
    await expectOutput(page,'Lookup failed');
    await pending('unmount');
    await page.evaluate(()=>{window.p6Unmount();window.p6Pending.find(entry=>entry.query==='unmount').resolve(['obsolete']);});
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    assert.deepEqual(await page.evaluate(()=>window.p6Publications),['fast','fail']);
    results.push({lesson:effectSlug,variant:'controlled out-of-order, rejection and unmount',publications:['fast','fail'],passed:true});
    await page.close();
    const strict=await pageFor(effectSlug,'strict');
    await strict.waitForFunction(()=>window.p6Pending.length===2);
    await strict.evaluate(()=>window.p6Pending.forEach(entry=>entry.resolve(['Result for strict'])));
    await expectOutput(strict,'Result for strict');
    assert.deepEqual(await strict.evaluate(()=>window.p6Publications),['strict']);
    results.push({lesson:effectSlug,variant:'development StrictMode replay',setups:2,publications:1,passed:true});
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({react:require(path.join(root,'web/node_modules/react/package.json')).version,browser:await browser.version(),results,errors},null,2));
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve=>server.close(resolve));
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
