// Signs in to the shared environment from QA_EMAIL and QA_PASSWORD, then waits for the person at the window to
// finish any 2FA or captcha. Neither value is logged. Copy it to profile/qa/login.mjs and set your sign-in
// form's selectors; QA.md § Sign-in names the variables and the driver command that runs it headed.
const EMAIL = process.env.QA_EMAIL;
const PASSWORD = process.env.QA_PASSWORD;
const SIGNING_IN = /^\/(login|verify)/; // the paths that still mean "not signed in yet", 2FA included

export const steps = [
  {
    name: 'sign in',
    screenshot: false, // a sign-in page can show a personal security image
    run: async ({ page, note }) => {
      if (!EMAIL || !PASSWORD) throw new Error('QA_EMAIL or QA_PASSWORD is empty');
      await page.goto('/login', { waitUntil: 'domcontentloaded', timeout: 90_000 });
      if (!SIGNING_IN.test(new URL(page.url()).pathname)) return note(`already signed in at ${page.url()}`);

      await page.locator('#email').fill(EMAIL, { timeout: 60_000 });
      const password = page.locator('#password');
      await password.fill(PASSWORD);
      await password.press('Enter');
      note('email and password entered, waiting for 2FA in the window');

      await page.waitForURL((url) => !SIGNING_IN.test(url.pathname), { timeout: 300_000 });
      await page.waitForLoadState('domcontentloaded');
      note(`landed: ${page.url()}`);
    },
  },
];
