/* Track only explicitly marked catalog actions, never arbitrary form data. */
(() => {
    "use strict";
    const root = document.getElementById("event-tracking");
    if (!root || !window.crypto || !window.crypto.randomUUID) return;
    const token = root.querySelector("[name=csrfmiddlewaretoken]");
    if (!token) return;
    const key = "library-events:" + root.dataset.user;
    let pending = [];
    try {
        const saved = JSON.parse(sessionStorage.getItem(key) || "[]");
        if (Array.isArray(saved)) pending = saved.filter(item => item && item.body && Date.now() - item.time < 86400000).slice(-50);
    } catch (_) { /* Storage may be disabled; tracking still works in memory. */ }
    let sending = false;
    function save() {
        try { sessionStorage.setItem(key, JSON.stringify(pending)); } catch (_) { /* Optional cache. */ }
    }
    async function flush() {
        if (sending || !pending.length || !navigator.onLine) return;
        sending = true;
        try {
            while (pending.length) {
                const item = pending[0];
                const response = await fetch(root.dataset.url, {
                    method: "POST", credentials: "same-origin", keepalive: true,
                    headers: {"Content-Type": "application/json", "X-CSRFToken": token.value},
                    body: JSON.stringify(item.body)
                });
                if (response.status === 202 || (response.status >= 400 && response.status < 500 && response.status !== 429)) {
                    pending.shift();
                    save();
                } else break;
            }
        } catch (_) { /* Retain the same event UUID for retry after navigation/network recovery. */ }
        finally { sending = false; }
    }
    document.addEventListener("click", event => {
        const target = event.target.closest("[data-track-event]");
        if (!target || target.hasAttribute("disabled")) return;
        const book = Number(target.dataset.bookId);
        if (!Number.isInteger(book) || book <= 0) return;
        pending.push({time: Date.now(), body: {
            event_id: window.crypto.randomUUID(), event_type: target.dataset.trackEvent,
            book_id: book, path: window.location.pathname
        }});
        pending = pending.slice(-50);
        save();
        void flush();
    });
    window.addEventListener("online", flush);
    window.setInterval(flush, 5000);
    void flush();
})();
