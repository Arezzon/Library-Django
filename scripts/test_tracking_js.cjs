const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const code = fs.readFileSync('library/events/static/events/tracking.js', 'utf8');

function browser({status = 202, saved = null, online = true, anonymous = false} = {}) {
    const handlers = {};
    const storage = new Map(saved ? [['library-events:7', JSON.stringify(saved)]] : []);
    const requests = [];
    const state = {status};
    const root = {dataset: {url: '/api/v1/events/', user: '7'}, querySelector: () => ({value: 'csrf'})};
    const context = {
        document: {getElementById: () => anonymous ? null : root, addEventListener: (name, callback) => {handlers[name] = callback;}},
        sessionStorage: {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value)},
        navigator: {onLine: online},
        window: {crypto: {randomUUID: () => '11111111-1111-4111-8111-111111111111'}, location: {pathname: '/book/'},
                 addEventListener: (name, callback) => {handlers[name] = callback;}, setInterval: callback => {handlers.interval = callback;}},
        fetch: async (url, options) => {requests.push({url, ...options}); return {status: state.status};},
    };
    vm.runInNewContext(code, context);
    return {handlers, storage, requests, state, context, click(book = '42') {
        handlers.click({target: {closest: () => ({dataset: {trackEvent: 'book_click', bookId: book}, hasAttribute: () => false})}});
    }};
}
const settle = () => new Promise(resolve => setImmediate(resolve));

test('marked click publishes only event schema with CSRF and keepalive', async () => {
    const page = browser();
    page.click();
    await settle();
    assert.equal(page.requests.length, 1);
    const request = page.requests[0];
    assert.equal(request.url, '/api/v1/events/');
    assert.equal(request.keepalive, true);
    assert.equal(request.headers['X-CSRFToken'], 'csrf');
    assert.deepEqual(JSON.parse(request.body), {event_id: '11111111-1111-4111-8111-111111111111', event_type: 'book_click', book_id: 42, path: '/book/'});
    assert.deepEqual(JSON.parse(page.storage.get('library-events:7')), []);
});

test('503 survives navigation and retries the same UUID', async () => {
    const page = browser({status: 503});
    page.click();
    await settle();
    const saved = JSON.parse(page.storage.get('library-events:7'));
    assert.equal(saved.length, 1);
    const next = browser({saved});
    await settle();
    assert.equal(JSON.parse(next.requests[0].body).event_id, saved[0].body.event_id);
    assert.deepEqual(JSON.parse(next.storage.get('library-events:7')), []);
});

test('offline clicks are retried when connection returns', async () => {
    const page = browser({online: false});
    page.click();
    await settle();
    assert.equal(page.requests.length, 0);
    page.context.navigator.onLine = true;
    await page.handlers.online();
    assert.equal(page.requests.length, 1);
});

test('anonymous pages and invalid book IDs send nothing', async () => {
    assert.equal(browser({anonymous: true}).handlers.click, undefined);
    const page = browser();
    page.click('invalid');
    await settle();
    assert.equal(page.requests.length, 0);
});
