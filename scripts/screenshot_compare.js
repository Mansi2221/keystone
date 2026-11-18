/**
 * Takes screenshots of the reference HTML and the live UI for comparison.
 * Also verifies demo user principal data.
 */
const { chromium } = require('/Users/mansi/keystone/ui-web/node_modules/playwright');
const path = require('path');

const MEDIA = path.resolve(__dirname, '..', 'docs', 'media');
const REF_HTML = 'file://' + path.resolve(__dirname, '..', 'docs', 'ui-reference.html');
const LIVE_URL = 'http://localhost:5173';

(async () => {
  const browser = await chromium.launch({ headless: true });

  // Screenshot reference
  console.log('1. Screenshotting reference HTML...');
  const refCtx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const refPage = await refCtx.newPage();
  await refPage.goto(REF_HTML);
  await refPage.waitForTimeout(500);
  await refPage.screenshot({ path: `${MEDIA}/ref-light.png` });
  console.log('   Saved ref-light.png');

  // Dark mode reference
  await refPage.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  await refPage.waitForTimeout(300);
  await refPage.screenshot({ path: `${MEDIA}/ref-dark.png` });
  console.log('   Saved ref-dark.png');
  await refCtx.close();

  // Screenshot live UI
  console.log('\n2. Screenshotting live UI...');
  const liveCtx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const livePage = await liveCtx.newPage();
  const errors = [];
  livePage.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
  livePage.on('pageerror', err => errors.push(err.message));

  await livePage.goto(LIVE_URL);
  await livePage.waitForSelector('.identity-card', { timeout: 15000 });
  await livePage.waitForTimeout(2000);
  await livePage.screenshot({ path: `${MEDIA}/live-light.png` });
  console.log('   Saved live-light.png');

  // Verify principal data for CEO
  const identityName = await livePage.locator('.identity-name').textContent();
  const identityTitle = await livePage.locator('.identity-title').textContent();
  console.log(`   Identity: ${identityName} / ${identityTitle}`);

  // Check demo personas section
  const personaCount = await livePage.locator('.section-label').count();
  console.log(`   Section labels: ${personaCount}`);

  // Check user cards
  const userCardCount = await livePage.locator('.user-card').count();
  console.log(`   User cards: ${userCardCount}`);

  // Dark mode
  const themeBtn = livePage.locator('.header-btn').first();
  await themeBtn.click();
  await livePage.waitForTimeout(500);
  await livePage.screenshot({ path: `${MEDIA}/live-dark.png` });
  console.log('   Saved live-dark.png');

  // Back to light
  await themeBtn.click();
  await livePage.waitForTimeout(300);

  // Verify all demo users
  console.log('\n3. Verifying demo user principals...');
  const demoUsers = await livePage.evaluate(async () => {
    const res = await fetch('/api/auth/demo-users');
    return res.json();
  });

  const expectedRoles = {
    ceo: 'executive',
    vp_sales: 'executive',
    vp_ops: 'executive',
    cfo: 'executive',
    vp_people: 'executive',
    cto: 'executive',
    sales_manager: 'manager',
    ops_manager: 'manager',
    hr_partner: 'hr_partner',
    finance_analyst: 'finance_analyst',
    sales_rep: 'sales_rep',
    engineer: 'individual_contributor',
    contractor: 'contractor',
  };

  let roleErrors = 0;
  for (const u of demoUsers) {
    const expected = expectedRoles[u.key];
    const ok = u.role === expected;
    if (!ok) {
      console.log(`   MISMATCH: ${u.key} expected role=${expected} got role=${u.role}`);
      roleErrors++;
    } else {
      console.log(`   OK: ${u.key} = ${u.role} (${u.department}) ${u.name}`);
    }
  }
  console.log(`   Role check: ${roleErrors === 0 ? 'ALL CORRECT' : `${roleErrors} ERRORS`}`);

  // Console errors
  console.log(`\nBrowser console errors: ${errors.length ? errors.join('; ') : 'None'}`);

  await browser.close();
})().catch(err => { console.error('FATAL:', err.message); process.exit(1); });
