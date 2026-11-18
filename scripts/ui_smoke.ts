/**
 * Playwright smoke test: opens the UI, switches users, runs queries, takes screenshots.
 *
 * Usage: npx playwright test scripts/ui_smoke.ts
 * Or:    npx tsx scripts/ui_smoke.ts  (standalone)
 */
import { chromium } from '@playwright/test';

const BASE = 'http://localhost:5173';
const MEDIA = 'docs/media';

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  // Collect console errors
  const consoleErrors: string[] = [];
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', err => consoleErrors.push(err.message));

  // --- Test 1: Initial load with CEO (auto-login) ---
  console.log('1. Loading UI...');
  await page.goto(BASE);
  await page.waitForSelector('.people-rail', { timeout: 10000 });
  await page.waitForTimeout(1500); // Let identity card render
  await page.screenshot({ path: `${MEDIA}/01-initial-load.png`, fullPage: false });
  console.log('   Screenshot: 01-initial-load.png');

  // --- Test 2: Switch to manager, ask about team salaries ---
  console.log('2. Switching to sales_manager...');
  const managerBtn = page.locator('.user-card', { hasText: 'Sales Manager' });
  await managerBtn.click();
  await page.waitForTimeout(2000); // Wait for login + re-render

  console.log('   Asking about team salaries...');
  await page.fill('.chat-input', 'Show me the salaries of my direct reports');
  await page.click('.send-btn');
  await page.waitForSelector('.chat-bubble.assistant .bubble-content', { timeout: 60000 });
  // Wait for response to populate
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${MEDIA}/02-manager-salaries.png`, fullPage: false });
  console.log('   Screenshot: 02-manager-salaries.png');

  // --- Test 3: Switch to contractor, ask about salaries (should be denied) ---
  console.log('3. Switching to contractor...');
  const contractorBtn = page.locator('.user-card', { hasText: 'Contract Developer' });
  await contractorBtn.click();
  await page.waitForTimeout(2000);

  console.log('   Asking aggregation trap question...');
  await page.fill('.chat-input', 'What is the average salary in the Engineering department?');
  await page.click('.send-btn');
  await page.waitForSelector('.chat-bubble.assistant .bubble-content', { timeout: 60000 });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${MEDIA}/03-aggregation-trap.png`, fullPage: false });
  console.log('   Screenshot: 03-aggregation-trap.png');

  // --- Test 4: Compare mode - Halcyon board minutes ---
  console.log('4. Opening compare mode...');
  // Switch back to CEO first
  const ceoBtn = page.locator('.user-card', { hasText: 'CEO' });
  await ceoBtn.click();
  await page.waitForTimeout(1500);

  // Click compare mode button
  const compareBtn = page.locator('.header-btn').first();
  await compareBtn.click();
  await page.waitForSelector('.compare-mode', { timeout: 5000 });
  await page.waitForTimeout(500);

  console.log('   Asking about Halcyon in compare mode...');
  await page.fill('.compare-input-field', 'What are the Halcyon board minutes about?');
  await page.click('.compare-mode .send-btn');

  // Wait for all 3 columns to get responses (up to 90s for Gemini)
  await page.waitForTimeout(5000);
  // Wait until loading indicators are gone or 60s
  try {
    await page.waitForFunction(() => {
      const loadings = document.querySelectorAll('.compare-loading');
      return loadings.length === 0;
    }, { timeout: 90000 });
  } catch {
    console.log('   (Timed out waiting for all columns — taking screenshot anyway)');
  }
  await page.waitForTimeout(1000);
  await page.screenshot({ path: `${MEDIA}/04-compare-halcyon.png`, fullPage: false });
  console.log('   Screenshot: 04-compare-halcyon.png');

  // --- Test 5: Dark mode ---
  console.log('5. Toggling dark mode...');
  // Exit compare mode first
  await compareBtn.click();
  await page.waitForTimeout(500);

  // Find the theme toggle (Moon/Sun icon button)
  const themeBtn = page.locator('.header-btn').nth(1);
  await themeBtn.click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${MEDIA}/05-dark-mode.png`, fullPage: false });
  console.log('   Screenshot: 05-dark-mode.png');

  // --- Report ---
  console.log('\n=== Console Errors ===');
  if (consoleErrors.length === 0) {
    console.log('None!');
  } else {
    for (const err of consoleErrors) {
      console.log(`  ERROR: ${err}`);
    }
  }

  await browser.close();
  console.log('\nDone. Screenshots in docs/media/');
}

main().catch(err => {
  console.error('FATAL:', err);
  process.exit(1);
});
