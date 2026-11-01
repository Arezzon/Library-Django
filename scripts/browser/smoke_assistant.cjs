// Disposable stack only: temporarily rename the catalog table to test source failure.
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright-core');
const {default: AxeBuilder} = require('@axe-core/playwright');
const base = process.env.ASSISTANT_BASE_URL || 'http://localhost:8000';
const compose = ['compose', '-f', process.env.ASSISTANT_COMPOSE_FILE || 'docker-compose-dev.yml'];
if (process.env.ASSISTANT_PROJECT) compose.push('-p', process.env.ASSISTANT_PROJECT);
const marker = 'private-assistant-browser-784603';
function sql(command) {
  return execFileSync('docker', [...compose, 'exec', '-T', 'db', 'psql', '-U', 'postgres', '-d', 'library_db', '-Atc', command], {encoding:'utf8'}).trim();
}
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.CHROME_PATH || undefined, args:['--no-sandbox']});
  try {
    const context = await browser.newContext({viewport:{width:1280,height:900}});
    const page = await context.newPage();
    await page.goto(base + '/authentication/login/');
    await page.locator('[name=email]').fill('reader@library.com');
    await page.locator('[name=password]').fill('reader123password');
    await Promise.all([page.waitForNavigation(), page.locator('form button[type=submit]').click()]);
    await page.goto(base + '/assistant/');
    const before = sql('SELECT (SELECT count(*) FROM order_order), (SELECT count(*) FROM order_reservation)');
    await page.locator('#id_q').focus();
    assert.equal(await page.locator(':focus').getAttribute('id'), 'id_q');
    await page.keyboard.type('Знайди твори Шевченка');
    await page.keyboard.press('Tab');
    assert.equal(await page.locator(':focus').innerText(), 'Ask');
    await Promise.all([page.waitForNavigation(), page.keyboard.press('Enter')]);
    assert.equal(new URL(page.url()).search, '');
    assert.match(await page.locator('#assistant-result').innerText(), /Kobzar/);
    assert(await page.locator('#assistant-result a[href^="/book/"]').count());
    const accessibility = await new AxeBuilder({page}).include('#assistant-interface').analyze();
    assert.deepEqual(accessibility.violations.map(v => ({id:v.id, nodes:v.nodes.map(n=>n.target)})), []);
    if (process.env.ASSISTANT_SCREENSHOT) await page.locator('#assistant-result').screenshot({path:process.env.ASSISTANT_SCREENSHOT});
    for (const question of ['Which of these are available?', 'Find books by Shevchenko', 'А які з них доступні?']) {
      await page.locator('#id_q').fill(question);
      const [answer]=await Promise.all([page.waitForNavigation(),page.getByRole('button',{name:'Ask',exact:true}).click()]);
      assert.equal(answer.status(),200);
      assert.match(await page.locator('#assistant-result').innerText(),/Kobzar/);
    }
    const source = page.locator('#assistant-result a[href^="/book/"]').first();
    await source.focus();
    await Promise.all([page.waitForNavigation(), page.keyboard.press('Enter')]);
    assert.match(new URL(page.url()).pathname, /^\/book\/\d+\/$/);
    await page.goto(base + '/assistant/');
    await page.locator('#id_q').fill(marker);
    await Promise.all([page.waitForNavigation(), page.getByRole('button',{name:'Ask',exact:true}).click()]);
    assert.match(await page.locator('#assistant-result').innerText(), /No matching records found/);
    assert.equal(new URL(page.url()).search, '');
    sql('ALTER TABLE book_book RENAME TO kan53_catalog_outage');
    try {
      await page.locator('#id_q').fill('Is Kobzar available?');
      const [response] = await Promise.all([page.waitForNavigation(), page.getByRole('button',{name:'Ask',exact:true}).click()]);
      assert.equal(response.status(), 503);
      assert.match(await page.locator('#assistant-result [role=alert]').innerText(), /The catalog is temporarily unavailable/);
      assert.equal(await page.locator('#assistant-result a[href^="/book/"]').count(), 0);
    } finally {
      sql('ALTER TABLE kan53_catalog_outage RENAME TO book_book');
    }
    const controls=JSON.parse(readFileSync(path.join(__dirname,'../../library/ai/control/questions_natural.json'),'utf8'));
    for (const control of controls) {
      await page.locator('#id_q').fill(control.question);
      const [answer]=await Promise.all([page.waitForNavigation(),page.getByRole('button',{name:'Ask',exact:true}).click()]);
      assert.equal(answer.status(),200,control.question);
      const titles=await page.locator('#assistant-result a').evaluateAll(links=>links.filter(a=>/^\/book\/\d+\/$/.test(a.getAttribute('href'))).map(a=>a.textContent.trim()).sort());
      assert.deepEqual(titles,[...control.titles].sort(),control.question);
    }
    const after = sql('SELECT (SELECT count(*) FROM order_order), (SELECT count(*) FROM order_reservation)');
    assert.equal(after, before);
    const logs = execFileSync('docker', [...compose, 'logs', '--no-color', 'web'], {encoding:'utf8'});
    assert(!logs.includes(marker), 'Private question leaked to logs');
    assert(logs.includes('status=source_unavailable'));
    console.log('PASS: 16 UA/EN questions, follow-ups, keyboard/source links, axe, source outage, private logs and unchanged loans/holds');
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode=1;});
