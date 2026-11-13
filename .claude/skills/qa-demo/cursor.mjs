// A visible pointer and step captions for a recorded browser run: Playwright's own mouse never
// shows on video. Call installCursor(context) before the first navigation; the helpers glide, then act.

const GLIDE_STEPS = 18;
const GLIDE_STEP_MS = 16;
const SETTLE_MS = 700;
const CAPTION_KEY = '__qaCaptionText';
const positions = new WeakMap();

// Runs in the page on every document the context opens, so the overlay survives navigations.
function overlay() {
  if (window.__qaOverlay) return;
  window.__qaOverlay = true;
  const remember = (key, value) => {
    try {
      sessionStorage.setItem(key, value);
    } catch {}
  };
  const recall = (key) => {
    try {
      return sessionStorage.getItem(key);
    } catch {
      return null;
    }
  };
  const mount = () => {
    if (!document.body) {
      requestAnimationFrame(mount);
      return;
    }
    const cursor = document.createElement('div');
    cursor.setAttribute('aria-hidden', 'true');
    cursor.style.cssText =
      'position:fixed;left:0;top:0;width:36px;height:36px;z-index:2147483647;pointer-events:none;transition:transform 60ms linear;';
    cursor.innerHTML =
      '<svg width="36" height="36" viewBox="0 0 24 24"><path d="M3 2l16 9.5-7 1.7L8.3 21z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    const ring = document.createElement('div');
    ring.setAttribute('aria-hidden', 'true');
    ring.style.cssText =
      'position:fixed;left:0;top:0;width:52px;height:52px;margin:-26px 0 0 -26px;border:4px solid #e8590c;border-radius:50%;z-index:2147483646;pointer-events:none;opacity:0;';
    const caption = document.createElement('div');
    caption.setAttribute('aria-hidden', 'true');
    caption.style.cssText =
      'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);max-width:80%;padding:14px 26px;border-radius:10px;background:rgba(17,17,17,.86);color:#fff;font:500 26px/1.4 system-ui,sans-serif;z-index:2147483647;pointer-events:none;display:none;';
    document.body.append(ring, cursor, caption);

    const place = (x, y) => {
      cursor.style.transform = `translate(${x}px, ${y}px)`;
      remember('__qaCursorAt', JSON.stringify([x, y]));
    };
    const saved = JSON.parse(recall('__qaCursorAt') || 'null');
    if (saved) place(saved[0], saved[1]);
    document.addEventListener('mousemove', (event) => place(event.clientX, event.clientY), { capture: true, passive: true });
    document.addEventListener(
      'mousedown',
      (event) => {
        ring.style.transition = 'none';
        ring.style.left = `${event.clientX}px`;
        ring.style.top = `${event.clientY}px`;
        ring.style.opacity = '1';
        ring.style.transform = 'scale(.6)';
        requestAnimationFrame(() => {
          ring.style.transition = 'opacity 450ms, transform 450ms';
          ring.style.opacity = '0';
          ring.style.transform = 'scale(1.5)';
        });
      },
      { capture: true, passive: true }
    );
    window.__qaCaption = (text) => {
      caption.textContent = text || '';
      caption.style.display = text ? 'block' : 'none';
    };
    window.__qaCaption(recall('__qaCaptionText'));
  };
  mount();
}

export async function installCursor(context) {
  await context.addInitScript(overlay);
}

/** Shows `text` in the caption bar, kept across navigations; an empty string hides it. */
export async function caption(page, text) {
  await page.evaluate(
    ([key, value]) => {
      try {
        sessionStorage.setItem(key, value);
      } catch {}
      window.__qaCaption?.(value);
    },
    [CAPTION_KEY, text]
  );
}

export async function hold(page, ms = SETTLE_MS) {
  await page.waitForTimeout(ms);
}

/** Glides the pointer to the centre of `locator`, slowly enough for a viewer to follow. */
export async function point(page, locator) {
  await locator.waitFor({ state: 'visible' });
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  if (!box) throw new Error(`point: ${locator} has no bounding box`);
  const [x0, y0] = positions.get(page) ?? [0, 0];
  const x1 = box.x + box.width / 2;
  const y1 = box.y + box.height / 2;
  for (let i = 1; i <= GLIDE_STEPS; i += 1) {
    const t = i / GLIDE_STEPS;
    const eased = t * (2 - t);
    await page.mouse.move(x0 + (x1 - x0) * eased, y0 + (y1 - y0) * eased);
    await page.waitForTimeout(GLIDE_STEP_MS);
  }
  positions.set(page, [x1, y1]);
  await hold(page, 250);
}

export async function click(page, locator) {
  await point(page, locator);
  await locator.click();
  await hold(page);
}

/** Opens a MUI select and chooses `option` by its visible name. */
export async function pick(page, combobox, option) {
  await click(page, combobox);
  await click(page, page.getByRole('option', { name: option, exact: true }));
}

export async function fill(page, locator, value) {
  await click(page, locator);
  await locator.fill(value);
  await hold(page);
}

export async function expectVisible(locator, { timeout = 10_000 } = {}) {
  await locator.waitFor({ state: 'visible', timeout });
}

/** Throws unless the trimmed text of `locator` becomes exactly `expected` within `timeout`. */
export async function expectText(locator, expected, { timeout = 10_000 } = {}) {
  const deadline = Date.now() + timeout;
  let seen = '';
  while (Date.now() < deadline) {
    seen = ((await locator.innerText().catch(() => '')) || '').trim();
    if (seen === expected) return;
    await new Promise((resolve) => {
      setTimeout(resolve, 200);
    });
  }
  throw new Error(`expected "${expected}", saw "${seen}"`);
}
