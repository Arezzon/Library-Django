// Disposable seeded stack: actual rating form, sessions, keyboard and validation.
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const {chromium} = require('playwright-core');
const {default: AxeBuilder} = require('@axe-core/playwright');
const base = process.env.RATINGS_BASE_URL || 'http://localhost:8000';
const dc = ['compose', '-f', process.env.RATINGS_COMPOSE_FILE || 'docker-compose-dev.yml'];
if (process.env.RATINGS_PROJECT) dc.push('-p', process.env.RATINGS_PROJECT);
function stockRows() {
  return execFileSync('docker',[...dc,'exec','-T','db','psql','-U','postgres','-d','library_db','-Atc','SELECT (SELECT count(*) FROM order_order), (SELECT count(*) FROM order_reservation)'],{encoding:'utf8'}).trim();
}
(async () => {
  const browser = await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH || undefined,args:['--no-sandbox']});
  let context;
  let page;
  let original;
  async function login() {
    context = await browser.newContext({viewport:{width:1280,height:1000}});
    page = await context.newPage();
    await page.goto(base+'/authentication/login/');
    await page.locator('[name=email]').fill('reader@library.com');
    await page.locator('[name=password]').fill('reader123password');
    await Promise.all([page.waitForNavigation(),page.locator('form button[type=submit]').click()]);
  }
  async function state() { return (await context.request.get(base+'/api/v1/books/1/rating/')).json(); }
  async function write(method,data) {
    const token=(await context.cookies()).find(c=>c.name==='csrftoken').value;
    const response=await context.request.fetch(base+'/api/v1/books/1/rating/',{method,data,headers:{'X-CSRFToken':token,Referer:base+'/book/1/'}});
    assert.equal(response.status(),200);
  }
  try {
    await login();
    original=(await state()).value;
    const before=stockRows();
    await write('DELETE');
    await page.goto(base+'/book/1/');
    assert.match(await page.locator('#book-rating').innerText(),/Your rating/);
    await page.locator('#rating-1').focus();
    for (let i=0;i<4;i++) await page.keyboard.press('ArrowRight');
    assert.equal(await page.locator('input[name=value]:checked').inputValue(),'5');
    await page.keyboard.press('Tab');
    assert.equal(await page.locator(':focus').innerText(),'Save rating');
    await Promise.all([page.waitForNavigation(),page.keyboard.press('Enter')]);
    assert.equal((await state()).value,5);
    let summary=await (await context.request.get(base+'/api/v1/books/1/rating-summary/')).json();
    assert.deepEqual(Object.keys(summary).sort(),['average','book_id','count']);
    const votes=summary.count;
    assert.equal(await page.locator('#book-rating').evaluate(el=>getComputedStyle(el).outlineStyle),'none');
    const scan=await new AxeBuilder({page}).include('#book-rating').analyze();
    assert.deepEqual(scan.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>n.target)})),[]);
    if(process.env.RATINGS_SCREENSHOT) await page.locator('#book-rating').screenshot({path:process.env.RATINGS_SCREENSHOT});
    await context.close();
    await login();
    await page.goto(base+'/book/1/');
    assert.equal(await page.locator('input[name=value]:checked').inputValue(),'5');
    await page.locator('#rating-5').focus();
    await page.keyboard.press('ArrowRight');
    assert.equal(await page.locator('input[name=value]:checked').inputValue(),'1');
    await page.keyboard.press('Tab');
    await Promise.all([page.waitForNavigation(),page.keyboard.press('Enter')]);
    assert.equal((await state()).value,1);
    summary=await (await context.request.get(base+'/api/v1/books/1/rating-summary/')).json();
    assert.equal(summary.count,votes);
    await page.locator('input[name=value]:checked').evaluate(input=>{input.value='6';});
    const [invalid]=await Promise.all([page.waitForNavigation(),page.getByRole('button',{name:'Save rating',exact:true}).click()]);
    assert.equal(invalid.status(),400);
    assert(await page.locator('#book-rating [role=alert]').isVisible());
    assert.equal((await state()).value,1);
    await Promise.all([page.waitForNavigation(),page.getByRole('button',{name:'Remove rating',exact:true}).click()]);
    assert.equal((await state()).value,null);
    assert.match(await page.locator('#book-rating').innerText(),/Your rating/);
    await page.locator('nav a[href="/book/recommendations/"]:visible').click();
    assert.equal(await page.locator('h1').innerText(),'For You');
    assert(await page.locator('article[data-book-id]').count());
    const recommendationsScan=await new AxeBuilder({page}).include('main').analyze();
    assert.deepEqual(recommendationsScan.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>n.target)})),[]);
    const html=await page.goto(base+'/api/v1/books/recommendations/?limit=5');
    assert.equal(html.status(),200);
    await page.setViewportSize({width:390,height:844});
    await page.goto(base+'/book/recommendations/');
    await page.locator('#mobile-menu-button').click();
    assert(await page.locator('#mobile-menu').getByRole('link',{name:'For You',exact:true}).isVisible());
    assert(await page.locator('#mobile-menu').getByRole('link',{name:'Assistant',exact:true}).isVisible());
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    assert.equal(stockRows(),before);
    console.log('PASS: rating keyboard CRUD, new login, aggregate privacy, axe, invalid form and unchanged loans/holds');
  } finally {
    try {
      if(context && original!==undefined) {
        if(original===null) await write('DELETE'); else await write('PUT',{value:original});
      }
    } finally { await browser.close(); }
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
