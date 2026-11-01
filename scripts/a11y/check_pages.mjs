// Accessibility check of the main pages (FR-041, FR-042). Each page is loaded in Chromium and
// checked by axe against WCAG 2.0, 2.1 and 2.2, levels A and AA. It prints every violation with
// its rule, impact, page and target, and exits 1 if there is one or a page cannot be reached.
//
//   node scripts/a11y/check_pages.mjs --base-url http://localhost:8000
//
// It signs in as the seeded demo reader and librarian, whose passwords are public.
// A11Y_READER_EMAIL, A11Y_READER_PASSWORD, A11Y_LIBRARIAN_EMAIL and A11Y_LIBRARIAN_PASSWORD
// override them. Forms are also checked with their errors, by submitting them empty or with an
// invalid value, which saves nothing. The one change it makes: when the reader holds no
// reservation, the reader reserves a book so the reservation pages show one, and cancels that
// reservation at the end.
import { parseArgs } from "node:util";
import { AxeBuilder } from "@axe-core/playwright";
import { chromium } from "playwright";

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const VIEWPORT = { width: 1280, height: 900 };

const { values } = parseArgs({
  options: { "base-url": { type: "string", default: "http://localhost:8000" } },
});
const base = values["base-url"].replace(/\/+$/, "");
const env = process.env;
const reader = {
  role: "reader",
  email: env.A11Y_READER_EMAIL || "reader@library.com",
  password: env.A11Y_READER_PASSWORD || "reader123password",
};
const librarian = {
  role: "librarian",
  email: env.A11Y_LIBRARIAN_EMAIL || "librarian@library.com",
  password: env.A11Y_LIBRARIAN_PASSWORD || "admin123password",
};

const violations = [];
const problems = [];
let checked = 0;

function where(page) {
  const url = new URL(page.url());
  return url.pathname + url.search;
}

async function open(page, target) {
  const response = await page.goto(new URL(target, base).href);
  if (!response?.ok()) {
    throw new Error(`${target} answered ${response ? response.status() : "nothing"}`);
  }
}

// Runs axe on the page as it is and records every violation.
async function check(page, name) {
  await page.evaluate(() => document.fonts.ready);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  checked += 1;
  for (const rule of result.violations) {
    for (const node of rule.nodes) {
      violations.push({
        page: name,
        rule: rule.id,
        impact: rule.impact,
        target: node.target.join(" "),
        help: rule.help,
      });
    }
  }
  console.log(`${result.violations.length ? "FAIL" : "ok  "} ${name}  ${where(page)}`);
}

// Records a failed step as a problem, so the remaining pages are still checked.
async function step(name, action) {
  try {
    await action();
  } catch (error) {
    const message = String(error.message).split("\n")[0];
    problems.push({ page: name, message });
    console.log(`ERR  ${name}  ${message}`);
  }
}

async function visit(page, name, target) {
  await step(name, async () => {
    await open(page, typeof target === "function" ? await target() : target);
    await check(page, name);
  });
}

// The first link on the current page whose path matches the pattern, or null.
async function link(page, pattern) {
  const hrefs = await page.locator("a[href]").evaluateAll((links) => links.map((a) => a.href));
  for (const href of hrefs) {
    const url = new URL(href);
    if (url.origin === new URL(base).origin && pattern.test(url.pathname)) {
      return url.pathname + url.search;
    }
  }
  return null;
}

async function linkFrom(page, from, pattern, what) {
  await open(page, from);
  const found = await link(page, pattern);
  if (!found) throw new Error(`no link to ${what} on ${where(page)}`);
  return found;
}

// Submits a form, empty apart from `fill`, without the browser's own validation, so the server
// answers with its errors.
async function submitInvalid(page, form, fill = {}) {
  for (const [name, value] of Object.entries(fill)) {
    await page.locator(`${form} [name=${name}]`).fill(value);
  }
  await Promise.all([
    page.waitForNavigation(),
    page.locator(form).evaluate((element) => {
      element.noValidate = true;
      element.requestSubmit();
    }),
  ]);
}

async function checkErrors(page, name, from, form, fill = {}) {
  await step(name, async () => {
    await open(page, from);
    await submitInvalid(page, form, fill);
    await check(page, name);
  });
}

// Signs in with the keyboard: the password, then Enter.
async function signIn(browser, account) {
  const page = await (await browser.newContext({ viewport: VIEWPORT })).newPage();
  await open(page, "/authentication/login/");
  await page.locator("input[name=email]").fill(account.email);
  await page.locator("input[name=password]").fill(account.password);
  await Promise.all([page.waitForNavigation(), page.locator("input[name=password]").press("Enter")]);
  if (where(page).startsWith("/authentication/login/")) {
    throw new Error(`the ${account.role} ${account.email} could not sign in`);
  }
  return page;
}

const RESERVATION_CANCEL = /^\/order\/reservations\/\d+\/cancel\/$/;

// Gives the reservation pages something to show. Returns true if it made a reservation.
async function reserveIfNone(page) {
  await open(page, "/order/reservations/");
  if (await link(page, RESERVATION_CANCEL)) return false;
  await open(page, "/book/");
  const hrefs = await page.locator("a[href]").evaluateAll((links) => links.map((a) => a.href));
  const books = [...new Set(hrefs.map((href) => new URL(href).pathname))].filter((path) =>
    /^\/book\/\d+\/$/.test(path),
  );
  for (const book of books) {
    await open(page, book);
    const reserve = page.locator('form[action^="/order/reserve/"] [type=submit]');
    if (await reserve.count()) {
      await Promise.all([page.waitForNavigation(), reserve.first().click()]);
      return true;
    }
  }
  throw new Error("the reader could not reserve any book");
}

const browser = await chromium.launch();
try {
  const visitor = await (await browser.newContext({ viewport: VIEWPORT })).newPage();
  const signInForm = "form:has(input[name=password])";
  await visit(visitor, "sign-in", "/authentication/login/");
  await checkErrors(visitor, "sign-in with errors", "/authentication/login/", signInForm);
  await visit(visitor, "registration", "/authentication/register/");
  await checkErrors(
    visitor,
    "registration with errors",
    "/authentication/register/",
    "form:has(input[name=confirm_password])",
  );

  let readerPage = null;
  let reserved = false;
  let readerProfile = null;
  await step("reader sign-in", async () => {
    readerPage = await signIn(browser, reader);
  });
  if (readerPage) {
    const page = readerPage;
    await visit(page, "home (reader)", "/");
    await visit(page, "catalog", "/book/");
    await visit(page, "catalog search", async () => {
      await open(page, "/book/");
      const title = (await page.locator('a[href^="/book/"][data-track-event]').first().innerText())
        .trim()
        .split(/\s+/)[0];
      return `/book/?q=${encodeURIComponent(title)}`;
    });
    await visit(page, "catalog filtered by author", async () => {
      await open(page, "/book/");
      const author = await page
        .locator("select[name=author_id] option:not([value=''])")
        .first()
        .getAttribute("value");
      return `/book/?author_id=${author}`;
    });
    await visit(page, "book page", () => linkFrom(page, "/book/", /^\/book\/\d+\/$/, "a book"));
    await visit(page, "my loans", "/order/my/");
    await step("reserving a book", async () => {
      reserved = await reserveIfNone(page);
    });
    await visit(page, "my reservations", "/order/reservations/");
    await visit(page, "cancelling my reservation", () =>
      linkFrom(page, "/order/reservations/", RESERVATION_CANCEL, "cancel a reservation"),
    );
    await visit(page, "my profile", async () => {
      readerProfile = await linkFrom(page, "/", /^\/authentication\/users\/\d+\/$/, "my profile");
      return readerProfile;
    });
    // The other pages in the reader's menu.
    await visit(page, "recommendations", "/book/recommendations/");
    await visit(page, "saved books", "/book/preferences/");
    await visit(page, "assistant", "/assistant/");
  }

  let librarianPage = null;
  await step("librarian sign-in", async () => {
    librarianPage = await signIn(browser, librarian);
  });
  if (librarianPage) {
    const page = librarianPage;
    const desk = "/order/reservations/desk/";
    await visit(page, "home (librarian)", "/");
    await visit(page, "reservation desk", desk);
    await visit(page, "issuing a reservation", () =>
      linkFrom(page, desk, /^\/order\/reservations\/\d+\/issue\/$/, "issue a reservation"),
    );
    await visit(page, "cancelling a reservation", () =>
      linkFrom(page, desk, RESERVATION_CANCEL, "cancel a reservation"),
    );
    await step("cancelling a reservation with errors", async () => {
      await open(page, await linkFrom(page, desk, RESERVATION_CANCEL, "cancel a reservation"));
      await submitInvalid(page, "form:has(textarea, input[name=reason])");
      await check(page, "cancelling a reservation with errors");
    });
    await visit(page, "all loans", "/order/all/");
    await visit(page, "loan editing", () =>
      linkFrom(page, "/order/all/", /^\/order\/update\/\d+\/$/, "edit a loan"),
    );
    await visit(page, "recording a return", () =>
      linkFrom(page, "/order/all/", /^\/order\/close\/\d+\/$/, "record a return"),
    );
    await visit(page, "user list", "/authentication/users/");
    const profile = async () =>
      readerProfile ??
      linkFrom(page, "/authentication/users/", /^\/authentication\/users\/\d+\/$/, "a user");
    await visit(page, "user details", profile);
    await visit(page, "user editing", async () =>
      linkFrom(page, await profile(), /^\/authentication\/users\/\d+\/update\/$/, "edit a user"),
    );
    await visit(page, "a reader's loans", async () =>
      linkFrom(page, await profile(), /^\/book\/user\/\d+\/$/, "the reader's loans"),
    );
    const book = () => linkFrom(page, "/book/", /^\/book\/\d+\/$/, "a book");
    await visit(page, "lending a book", async () =>
      linkFrom(page, await book(), /^\/order\/lend\/$/, "lend the book"),
    );
    await visit(page, "new book", "/book/create/");
    // A book's title may be empty, so a negative number of copies is the error.
    await checkErrors(page, "new book with errors", "/book/create/", "form:has(input[name=name])", {
      count: "-1",
    });
    await visit(page, "book editing", async () =>
      linkFrom(page, await book(), /^\/book\/update\/\d+\/$/, "edit the book"),
    );
    await visit(page, "deleting a book", async () => {
      const edit = await linkFrom(page, await book(), /^\/book\/update\/\d+\/$/, "edit the book");
      return linkFrom(page, edit, /^\/book\/delete\/\d+\/$/, "delete the book");
    });
    await visit(page, "authors", "/author/");
    await visit(page, "new author", "/author/create/");
    await checkErrors(
      page,
      "new author with errors",
      "/author/create/",
      "form:has(input[name=surname])",
    );
    await visit(page, "author editing", () =>
      linkFrom(page, "/author/", /^\/author\/update\/\d+\/$/, "edit an author"),
    );
    await visit(page, "deleting an author", () =>
      linkFrom(page, "/author/", /^\/author\/delete\/\d+\/$/, "delete an author"),
    );
    await visit(page, "analytics dashboard", "/events/");
  }

  if (reserved) {
    await step("cancelling the check's reservation", async () => {
      const page = readerPage;
      await open(page, await linkFrom(page, "/order/reservations/", RESERVATION_CANCEL, "cancel"));
      await Promise.all([
        page.waitForNavigation(),
        page.getByRole("button", { name: /cancel reservation/i }).click(),
      ]);
    });
  }
} finally {
  await browser.close();
}

console.log(
  `\nChecked ${checked} pages: ${violations.length} violations, ` +
    `${problems.length} pages or steps that could not be checked.`,
);
for (const v of violations) {
  console.log(`- ${v.page}: ${v.rule} (${v.impact}) at ${v.target}: ${v.help}`);
}
for (const p of problems) {
  console.log(`- ${p.page}: ${p.message}`);
}
process.exitCode = violations.length || problems.length ? 1 : 0;
