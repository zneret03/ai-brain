// Upload the files a PR body names as ![alt](evidence:<file>) and swap in GitHub's links (docs/SPRINTS.md § Evidence).
// GitHub has no API for PR attachments, so this uses the attachment box of the PR page, signed in as the user.
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, realpathSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const AUTH = join(HERE, '.auth', 'github.json');
const PLACEHOLDER = /!\[([^\]]*)\]\(evidence:([^)\s]+)\)/g;
const VIDEO = /\.(mp4|mov|webm)$/i;
const ASSET = /https:\/\/github\.com\/user-attachments\/(?:assets|files)\/[\w/.-]+/g;

const die = (msg, code = 1) => {
  console.error(`pr-images: ${msg}`);
  process.exit(code);
};

export function placeholders(body) {
  return [...new Set([...body.matchAll(PLACEHOLDER)].map((m) => m[2]))];
}

export function rewrite(body, urls) {
  return body.replace(PLACEHOLDER, (whole, alt, file) => {
    const url = urls[file];
    if (!url) return whole;
    return VIDEO.test(file) ? `\n${url}\n` : `![${alt}](${url})`; // GitHub plays a bare video link inline
  });
}

async function chromium() {
  try {
    return (await import('playwright')).chromium;
  } catch {
    return die('Playwright is missing: npm ci --prefix ai-brain/evidence && npx --prefix ai-brain/evidence playwright install chromium', 3);
  }
}

async function login() {
  const browser = await (await chromium()).launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto('https://github.com/login');
  console.log('Sign in to GitHub in the window that opened; this waits until you are signed in.');
  await page.waitForURL((u) => u.hostname === 'github.com' && !/^\/(login|session|sessions)/.test(u.pathname), {
    timeout: 10 * 60_000,
  });
  mkdirSync(dirname(AUTH), { recursive: true });
  await context.storageState({ path: AUTH });
  await browser.close();
  console.log(`signed in: the session is in ${AUTH}. It is a credential: never share it, delete it to sign out.`);
}

export async function commentBox(page) {
  for (const sel of ['textarea#new_comment_field', 'textarea[name="comment[body]"]', 'textarea[placeholder*="comment" i]']) {
    const box = page.locator(sel).last();
    if (await box.count()) return box;
  }
  return die(`no comment box on ${page.url()}: is the session still signed in? (pr-images --login)`, 4);
}

export async function uploadOne(page, box, path) {
  await box.fill('');
  const input = box.locator('xpath=ancestor::*[.//input[@type="file"]][1]//input[@type="file"]').first();
  await input.setInputFiles(path);
  const handle = await box.elementHandle();
  await page.waitForFunction(
    (el) => /user-attachments\/(assets|files)\//.test(el.value) && !/Uploading/.test(el.value),
    handle,
    { timeout: 120_000 },
  );
  const url = ((await box.inputValue()).match(ASSET) || []).pop();
  await box.fill(''); // never post the scratch comment
  if (!url) die(`GitHub gave no link for ${path}`, 5);
  return url;
}

async function main(argv) {
  if (argv[0] === '--login') return login();
  const [target, dir, flag] = argv;
  const m = /^([\w.-]+)\/([\w.-]+)#(\d+)$/.exec(target || '');
  if (!m || !dir) die('usage: pr-images <owner>/<repo>#<n> <evidence-dir> [--dry-run] | --login', 2);
  const [, owner, repo, number] = m;
  const gh = (...args) => execFileSync('gh', args, { encoding: 'utf8' });
  const body = JSON.parse(gh('pr', 'view', number, '-R', `${owner}/${repo}`, '--json', 'body')).body || '';
  const files = placeholders(body);
  if (!files.length) return console.log('nothing to upload: the body has no ![alt](evidence:<file>) placeholder');
  const missing = files.filter((f) => !existsSync(resolve(dir, f)));
  if (missing.length) die(`not in ${dir}: ${missing.join(', ')}`, 2);
  if (flag === '--dry-run') {
    for (const f of files) console.log(`would upload  ${f}  (${Math.round(statSync(resolve(dir, f)).size / 1024)} KB)`);
    return;
  }
  if (!existsSync(AUTH)) die('no GitHub session: run pr-images --login once', 4);
  const browser = await (await chromium()).launch();
  const page = await (await browser.newContext({ storageState: AUTH })).newPage();
  await page.goto(`https://github.com/${owner}/${repo}/pull/${number}`, { waitUntil: 'domcontentloaded' });
  const box = await commentBox(page);
  const urls = {};
  for (const f of files) {
    urls[f] = await uploadOne(page, box, resolve(dir, f));
    console.log(`uploaded  ${f}`);
  }
  await browser.close();
  execFileSync('gh', ['pr', 'edit', number, '-R', `${owner}/${repo}`, '--body-file', '-'], { input: rewrite(body, urls) });
  console.log(`rewrote the body of ${owner}/${repo}#${number}: ${files.length} file(s)`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) {
  main(process.argv.slice(2)).catch((e) => die(e.message || String(e)));
}
