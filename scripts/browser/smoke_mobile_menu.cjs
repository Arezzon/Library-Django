// Exercise the real disclosure and role-specific navigation in a seeded stack.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright-core');
const {default: AxeBuilder} = require('@axe-core/playwright');
const base = process.env.MOBILE_MENU_BASE_URL || 'http://localhost:8000';
const screenshots = process.env.MOBILE_MENU_SCREENSHOT_DIR;
const destinations = {
  'Home':'/', 'Books Catalog':'/book/', 'For You':'/book/recommendations/',
  'Assistant':'/assistant/', 'Saved Books':'/book/preferences/',
  'My Orders':'/order/my/', 'My Reservations':'/order/reservations/',
  'Reservation Desk':'/order/reservations/desk/', 'Analytics':'/events/',
  'Authors':'/author/', 'Users':'/authentication/users/', 'All Orders':'/order/all/',
  'Log In':'/authentication/login/', 'Register':'/authentication/register/'
};
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.CHROME_PATH || undefined, args:['--no-sandbox']});
  try {
    for (const role of ['guest', 'reader', 'librarian']) {
      for (const width of [320, 375]) {
        const context = await browser.newContext({viewport:{width, height:720}});
        try {
          const page = await context.newPage();
          await page.goto(base + '/authentication/login/');
          if (role !== 'guest') {
            await page.locator('[name=email]').fill(role + '@library.com');
            await page.locator('[name=password]').fill(role === 'reader' ? 'reader123password' : 'admin123password');
            await Promise.all([page.waitForNavigation(), page.locator('form button[type=submit]').click()]);
          }
          const toggle = page.locator('#mobile-menu-button');
          const menu = page.locator('#mobile-menu');
          await toggle.waitFor({state:'visible'});
          await page.waitForFunction(() => getComputedStyle(document.querySelector('#hamburger-icon-open')).width === '24px');
          assert.equal(await toggle.getAttribute('aria-controls'), 'mobile-menu');
          assert.equal(await toggle.getAttribute('aria-expanded'), 'false');
          assert.equal(await menu.isVisible(), false);
          await toggle.focus();
          await page.keyboard.press('Enter');
          assert.equal(await toggle.getAttribute('aria-expanded'), 'true');
          await page.keyboard.press('Tab');
          assert.equal(await page.locator(':focus').evaluate(el => !!el.closest('#mobile-menu')), true);
          assert.ok(await page.locator(':focus').evaluate(el => {const s=getComputedStyle(el);return s.outlineStyle !== 'none' || s.boxShadow !== 'none';}));
          const common = ['Your profile','Home','Books Catalog','For You','Assistant','Saved Books'];
          const reader = ['My Orders','My Reservations'];
          const librarian = ['Reservation Desk','Analytics','Authors','Users','All Orders'];
          const expected = role === 'guest' ? ['Log In','Register'] : [...common,...(role === 'reader' ? reader : librarian),'Log Out'];
          const controls = menu.locator('a, button');
          assert.deepEqual(await controls.allTextContents().then(xs => xs.map(x => x.trim())), expected);
          for (const control of await controls.all()) {
            const label = (await control.innerText()).trim();
            assert.equal(await menu.getByRole(label === 'Log Out' ? 'button' : 'link',{name:label,exact:true}).count(),1);
            const svg = control.locator('svg');
            assert.equal(await svg.count(),1);
            assert.equal(await svg.getAttribute('aria-hidden'),'true');
            assert.equal(await svg.getAttribute('focusable'),'false');
            assert.deepEqual(await svg.evaluate(el => {const s=getComputedStyle(el);return [s.width,s.height,s.marginRight,s.flexShrink,s.stroke];}), ['16px','16px','10px','0',await control.evaluate(el=>getComputedStyle(el).color)]);
            const box = await control.boundingBox();
            assert.ok(box.x >= 0 && box.x + box.width <= width);
          }
          for (const link of await menu.locator('a').all()) {
            const href = await link.getAttribute('href');
            const label = (await link.innerText()).trim();
            if (label === 'Your profile') assert.match(href,/^\/authentication\/users\/\d+\/$/);
            else assert.equal(href,destinations[label]);
            const response = await context.request.get(new URL(href,base).href);
            assert.equal(response.status(),200,await link.innerText());
          }
          if (role !== 'guest') {
            const form = menu.locator('form');
            assert.equal(await form.getAttribute('method'),'post');
            assert.equal(await form.getAttribute('action'),'/authentication/logout/');
            assert.ok(await form.locator('[name=csrfmiddlewaretoken]').inputValue());
          }
          const scan = await new AxeBuilder({page}).include('header').analyze();
          assert.deepEqual(scan.violations.map(v=>({id:v.id,targets:v.nodes.map(n=>n.target)})),[]);
          if (screenshots) {
            fs.mkdirSync(screenshots,{recursive:true});
            await page.screenshot({path:path.join(screenshots,`${role}-${width}.png`)});
          }
          await toggle.focus();
          await page.keyboard.press('Space');
          assert.equal(await menu.isVisible(),false);
          assert.equal(await toggle.getAttribute('aria-expanded'),'false');
          await toggle.click();
          assert.equal(await menu.isVisible(),true);
          for (const control of await controls.all()) {
            await page.keyboard.press('Tab');
            assert.equal(await control.evaluate(el => el === document.activeElement),true);
            assert.ok(await control.evaluate(el => {const s=getComputedStyle(el);return s.outlineStyle !== 'none' || s.boxShadow !== 'none';}), 'each item shows keyboard focus');
          }
          const last = await controls.last().boundingBox();
          assert.ok(last.y >= 0 && last.y + last.height <= 720, 'last item remains visible when focused');
          if (screenshots && role === 'librarian') {
            await page.screenshot({path:path.join(screenshots,`${role}-${width}-bottom.png`)});
          }
          await page.keyboard.press('Tab');
          assert.equal(await page.locator(':focus').evaluate(el=>!!el.closest('#mobile-menu')),false);
          console.log(`${role} ${width}px: roles, destinations, icons, keyboard, focus and axe passed`);
        } finally { await context.close(); }
      }
    }
  } finally { await browser.close(); }
})().catch(error => {console.error(error);process.exitCode=1;});
