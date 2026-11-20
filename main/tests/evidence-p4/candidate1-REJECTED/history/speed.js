const { chromium } = require('playwright');
(async () => {
  const url = process.env.PS_URL, b = await chromium.launch(), ctx = await b.newContext(); await ctx.route(/^https?:\/\/(?!localhost)/, r => r.abort());
  const page = await ctx.newPage(); const errs = []; page.on('pageerror', e => errs.push(String(e)));
  await page.goto(url); await page.waitForFunction(() => typeof S !== 'undefined' && document.querySelector('#speedBtn'));
  const before = await page.evaluate(() => ({ rate: S.rate, label: document.querySelector('#speedBtn').textContent }));
  await page.click('#speedBtn'); await page.click('#speedPop .chip[data-v="1.25"]'); await new Promise(r => setTimeout(r, 300));
  const after = await page.evaluate(() => ({ rate: S.rate, label: document.querySelector('#speedBtn').textContent, on: [...document.querySelectorAll('#speedPop .chip.on')].map(c => c.dataset.v) }));
  console.log(JSON.stringify({ before, after, errs }));
  await b.close();
})();
