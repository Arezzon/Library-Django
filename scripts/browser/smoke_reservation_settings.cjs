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
    function localDeadline(iso) {
      const parts = new Intl.DateTimeFormat('en-GB',{
        timeZone:'Europe/Kyiv',day:'numeric',month:'numeric',year:'numeric',
        hour:'2-digit',minute:'2-digit',hourCycle:'h23',timeZoneName:'shortOffset'
      }).formatToParts(new Date(iso));
      const fields=Object.fromEntries(parts.map(p=>[p.type,p.value]));
      const months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
      const zone=fields.timeZoneName==='GMT+2'?'EET':'EEST';
      assert.ok(['GMT+2','GMT+3'].includes(fields.timeZoneName));
      return `${Number(fields.day)} ${months[Number(fields.month)-1]} ${fields.year}, ${fields.hour}:${fields.minute} ${zone}`;
    }
    for (const held of [first,second]) {
      const time=readerPage.locator(`time[data-reservation-deadline="${held.id}"]`);
      assert.equal(Date.parse(await time.getAttribute('datetime')),Date.parse(held.expires_at));
      assert.equal((await time.innerText()).trim(),localDeadline(held.expires_at));
    }
    assert.ok((await readerPage.getByRole('status').innerText()).includes(
      `Reserved “Zakhar Berkut”. Collect it from a librarian before ${localDeadline(second.expires_at)}.`
    ));
    const readerScan=await new AxeBuilder({page:readerPage}).include('main').analyze();
    assert.deepEqual(readerScan.violations.map(v=>({id:v.id,targets:v.nodes.map(n=>n.target)})),[]);
    if(process.env.RESERVATION_DEADLINE_SCREENSHOT_DIR) {
      fs.mkdirSync(process.env.RESERVATION_DEADLINE_SCREENSHOT_DIR,{recursive:true});
      await readerPage.setViewportSize({width:1440,height:900});
      await readerPage.screenshot({path:path.join(process.env.RESERVATION_DEADLINE_SCREENSHOT_DIR,'deadlines-1440.png')});
      const mainBox=await readerPage.locator('main').boundingBox();
      const tableBox=await readerPage.locator('.table-wrapper').boundingBox();
      await readerPage.screenshot({clip:{x:mainBox.x,y:mainBox.y,width:mainBox.width,height:tableBox.y+tableBox.height-mainBox.y+24},path:path.join(process.env.RESERVATION_DEADLINE_SCREENSHOT_DIR,'deadlines-content.png')});
    }
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
    console.log('Settings persistence, bounds, roles, CSRF, keyboard, axe, localized confirmation/list and API deadlines passed.');
  } finally {
    if(reader) for(const id of holds) assert.equal((await post(reader,base+`/api/v1/reservation/${id}/cancel/`,{})).status(),200);
    if(page && original) await save(original);
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
