// Real librarian settings, CSRF, reader reservations and persistent deadlines.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright-core');
const {default: AxeBuilder} = require('@axe-core/playwright');
const base = process.env.RESERVATION_SETTINGS_BASE_URL || 'http://localhost:8000';
const url = base + '/order/reservations/settings/';
(async () => {
  const browser = await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH || undefined,args:['--no-sandbox']});
  const holds = [];
  let librarian, reader, page, original;
  async function login(role) {
    const context = await browser.newContext({viewport:{width:375,height:812}});
    const tab = await context.newPage();
    await tab.goto(base+'/authentication/login/');
    await tab.locator('[name=email]').fill(role+'@library.com');
    await tab.locator('[name=password]').fill(role==='reader'?'reader123password':'admin123password');
    await Promise.all([tab.waitForNavigation(),tab.locator('form button[type=submit]').click()]);
    return [context,tab];
  }
  async function save(hours) {
    await page.goto(url);
    await page.locator('[name=hours]').fill(String(hours));
    await Promise.all([page.waitForNavigation(),page.getByRole('button',{name:'Save Settings',exact:true}).click()]);
    assert.equal(await page.locator('[name=hours]').inputValue(),String(hours));
  }
  async function post(context, destination, data, csrf=true) {
    const token = (await context.cookies()).find(c=>c.name==='csrftoken').value;
    return context.request.post(destination,{data,headers:csrf?{'X-CSRFToken':token,Referer:url}:{}});
  }
  try {
    [librarian,page] = await login('librarian');
    await page.goto(base+'/order/reservations/desk/');
    await page.getByRole('link',{name:'Reservation Settings',exact:true}).click();
    original = Number(await page.locator('[name=hours]').inputValue());
    assert.equal(await page.locator('[name=hours]').getAttribute('min'),'1');
    assert.equal(await page.locator('[name=hours]').getAttribute('max'),'168');
    await page.locator('[name=hours]').focus();
    await page.keyboard.press('Tab');
    assert.equal(await page.locator(':focus').innerText(),'Back to Desk');
    await page.keyboard.press('Tab');
    assert.equal(await page.locator(':focus').innerText(),'Save Settings');
    const scan = await new AxeBuilder({page}).include('main').analyze();
    assert.deepEqual(scan.violations.map(v=>({id:v.id,targets:v.nodes.map(n=>n.target)})),[]);
    assert.equal((await post(librarian,url,{hours:1},false)).status(),403);
    const token=(await librarian.cookies()).find(c=>c.name==='csrftoken').value;
    assert.equal((await librarian.request.post(url,{form:{hours:169},headers:{'X-CSRFToken':token,Referer:url}})).status(),400);
    await page.goto(url);
    assert.equal(Number(await page.locator('[name=hours]').inputValue()),original);
    await save(1);
    const [readerContext,readerPage] = await login('reader');
    reader = readerContext;
    assert.equal((await reader.request.get(url)).status(),404);
    assert.equal((await post(reader,url,{hours:168})).status(),404);
    const result=await post(reader,base+'/api/v1/reservation/',{book:2});
    assert.equal(result.status(),201);
    const first=await result.json();
    holds.push(first.id);
    assert.equal(Date.parse(first.expires_at)-Date.parse(first.created_at),3600000);
    await save(168);
    await readerPage.goto(base+'/book/3/');
    const reserve=readerPage.getByRole('button',{name:'Reserve for 168 Hours',exact:true});
    await Promise.all([readerPage.waitForNavigation(),reserve.click()]);
    const reservations=await (await reader.request.get(base+'/api/v1/reservation/')).json();
    const rows=Array.isArray(reservations)?reservations:reservations.results;
    const second=rows.find(r=>r.book===3);
    assert.ok(second);
    holds.push(second.id);
    assert.equal(Date.parse(second.expires_at)-Date.parse(second.created_at),168*3600000);
    const unchanged=await (await reader.request.get(base+`/api/v1/reservation/${first.id}/`)).json();
    assert.equal(unchanged.expires_at,first.expires_at);
    await page.goto(url);
    await page.reload();
    assert.equal(await page.locator('[name=hours]').inputValue(),'168');
    if(process.env.RESERVATION_SETTINGS_SCREENSHOT_DIR) {
      fs.mkdirSync(process.env.RESERVATION_SETTINGS_SCREENSHOT_DIR,{recursive:true});
      await page.screenshot({path:path.join(process.env.RESERVATION_SETTINGS_SCREENSHOT_DIR,'settings-375.png')});
      await page.setViewportSize({width:1280,height:900});
      await page.screenshot({path:path.join(process.env.RESERVATION_SETTINGS_SCREENSHOT_DIR,'settings-desktop.png')});
      await page.locator('main .card').screenshot({path:path.join(process.env.RESERVATION_SETTINGS_SCREENSHOT_DIR,'settings-card.png')});
    }
    const guest=await browser.newContext();
    const response=await guest.request.get(url);
    assert.ok(response.url().includes('/authentication/login/'));
    await guest.close();
    console.log('Settings persistence, bounds, roles, CSRF, keyboard, axe and web/API deadlines passed.');
  } finally {
    if(reader) for(const id of holds) assert.equal((await post(reader,base+`/api/v1/reservation/${id}/cancel/`,{})).status(),200);
    if(page && original) await save(original);
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
