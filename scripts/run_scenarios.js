/**
 * Run all 7 demo scenarios + compare mode against the live API.
 * Requires: API on :8000, Vite on :5173, both with PROFILE=free.
 *
 * Usage: node scripts/run_scenarios.js
 */
const { chromium } = require('/Users/mansi/keystone/ui-web/node_modules/playwright');
const path = require('path');

const MEDIA = path.resolve(__dirname, '..', 'docs', 'media');
const BASE = 'http://localhost:5173';
const TIMEOUT = 180000; // 3 min per query (Gemini rate limits)

const scenarios = [
  {
    id: 1,
    name: 'CEO salary (own data)',
    user: 'ceo',
    query: 'What is my salary?',
    expect: 'should_answer',
    screenshot: '01-ceo-salary.png',
  },
  {
    id: 2,
    name: 'Manager team salaries',
    user: 'ops_manager',
    query: 'Show me the salaries of my direct reports',
    expect: 'should_answer',
    screenshot: '02-manager-salaries.png',
  },
  {
    id: 3,
    name: 'Contractor aggregation trap',
    user: 'contractor',
    query: 'What is the average salary in the Engineering department?',
    expect: 'should_deny',
    screenshot: '03-aggregation-trap.png',
  },
  {
    id: 4,
    name: 'Halcyon board minutes (CEO)',
    user: 'ceo',
    query: 'What are the Halcyon board minutes about?',
    expect: 'should_answer',
    screenshot: '04-halcyon-ceo.png',
  },
  {
    id: 5,
    name: 'Halcyon board minutes (contractor - denied)',
    user: 'contractor',
    query: 'What are the Halcyon board minutes about?',
    expect: 'should_deny',
    screenshot: '05-halcyon-contractor.png',
  },
  {
    id: 6,
    name: 'Brightline escalation (ops_manager)',
    user: 'ops_manager',
    query: 'Show me ticket TKT-2291 and any related deals',
    expect: 'should_answer',
    screenshot: '06-brightline-escalation.png',
  },
  {
    id: 7,
    name: 'Ops-alerts chat (CEO)',
    user: 'ceo',
    query: 'Show me recent messages in #ops-alerts',
    expect: 'should_answer',
    screenshot: '07-ops-alerts.png',
  },
];

async function freshPage(page, userKey) {
  // Full page reload to clear any stuck state
  await page.goto(BASE);
  await page.waitForSelector('.identity-card', { timeout: 15000 });
  await page.waitForTimeout(2000);
  await loginAs(page, userKey);
}

async function loginAs(page, userKey) {
  const label = userKey === 'ceo' ? 'CEO' : userKey === 'ops_manager' ? 'Operations Manager' : userKey === 'contractor' ? 'Contract Developer' : userKey;
  await page.locator(`.user-card`, { hasText: label }).click();
  await page.waitForTimeout(2000);
  // Wait for chat input to become enabled
  await page.waitForSelector('.chat-input:not([disabled])', { timeout: 10000 }).catch(() => {});
}

async function sendAndWait(page, query) {
  // Ensure input is enabled before typing
  await page.waitForSelector('.chat-input:not([disabled])', { timeout: 15000 });
  await page.fill('.chat-input', query);
  await page.click('.send-btn');

  try {
    await page.waitForFunction(() => {
      const bubbles = document.querySelectorAll('.chat-bubble.assistant .bubble-content');
      const last = bubbles[bubbles.length - 1];
      return last && last.textContent && last.textContent.length > 20;
    }, { timeout: TIMEOUT });
    await page.waitForTimeout(1500);
    return true;
  } catch {
    return false;
  }
}

function getResponseText(page) {
  return page.evaluate(() => {
    const bubbles = document.querySelectorAll('.chat-bubble.assistant .bubble-content');
    const last = bubbles[bubbles.length - 1];
    return last ? last.textContent.substring(0, 500) : 'NO CONTENT';
  });
}

function getToolSteps(page) {
  return page.evaluate(() => {
    const steps = document.querySelectorAll('.tool-step');
    return Array.from(steps).map(s => ({
      tool: s.querySelector('.tool-step-name')?.textContent || '',
      status: s.querySelector('.tool-step-pill')?.textContent || '',
    }));
  });
}

function hasBlocked(page) {
  return page.evaluate(() => !!document.querySelector('.blocked-warning'));
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const errors = [];
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
  page.on('pageerror', err => errors.push(err.message));

  await page.goto(BASE);
  await page.waitForSelector('.identity-card', { timeout: 15000 });
  await page.waitForTimeout(2000);

  const results = [];

  for (let i = 0; i < scenarios.length; i++) {
    const scenario = scenarios[i];
    console.log(`\n--- Scenario ${scenario.id}: ${scenario.name} ---`);

    // Rate limit spacing: wait 15s between queries to avoid Gemini 429s
    if (i > 0) {
      console.log('  Waiting 15s for rate limit cooldown...');
      await page.waitForTimeout(15000);
    }

    // Fresh page load for each scenario to avoid stuck state
    await freshPage(page, scenario.user);

    console.log(`  Asking: ${scenario.query}`);
    const responded = await sendAndWait(page, scenario.query);

    const response = await getResponseText(page);
    const steps = await getToolSteps(page);
    const blocked = await hasBlocked(page);

    await page.screenshot({ path: `${MEDIA}/${scenario.screenshot}` });
    console.log(`  Screenshot: ${scenario.screenshot}`);
    console.log(`  Responded: ${responded}`);
    console.log(`  Blocked: ${blocked}`);
    console.log(`  Steps: ${JSON.stringify(steps.map(s => `${s.tool}:${s.status}`))}`);
    console.log(`  Response: ${response.substring(0, 200)}`);

    // Check permission matrix
    let verdict = 'UNKNOWN';
    if (scenario.expect === 'should_answer') {
      if (responded && !blocked && response.length > 30) {
        verdict = 'PASS';
      } else if (!responded) {
        verdict = 'TIMEOUT (rate limited)';
      } else {
        verdict = 'FAIL — should have answered';
      }
    } else if (scenario.expect === 'should_deny') {
      if (blocked) {
        verdict = 'PASS (blocked)';
      } else if (response.toLowerCase().includes('denied') || response.toLowerCase().includes('access') || response.toLowerCase().includes('permission') || response.toLowerCase().includes('cannot')) {
        verdict = 'PASS (denied in response)';
      } else if (!responded) {
        verdict = 'TIMEOUT (rate limited)';
      } else {
        verdict = 'FAIL — should have been denied';
      }
    }
    console.log(`  VERDICT: ${verdict}`);
    results.push({ ...scenario, verdict, response: response.substring(0, 200) });
  }

  // --- Compare mode ---
  console.log('\n--- Compare Mode: Halcyon board minutes ---');
  // Switch to CEO first
  await loginAs(page, 'ceo');
  await page.waitForTimeout(1000);

  // Toggle compare mode
  await page.click('.compare-switch');
  await page.waitForSelector('.compare-mode', { timeout: 5000 });

  await page.fill('.compare-input-field', 'What are the Halcyon board minutes about?');
  await page.click('.compare-mode .send-btn');

  // Wait for all columns (up to 3 min)
  try {
    await page.waitForFunction(() => {
      const loadings = document.querySelectorAll('.compare-loading');
      return loadings.length === 0;
    }, { timeout: TIMEOUT });
  } catch {
    console.log('  Some columns timed out');
  }
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${MEDIA}/08-compare-halcyon.png` });
  console.log('  Screenshot: 08-compare-halcyon.png');

  // Check column contents
  const columns = await page.evaluate(() => {
    const cols = document.querySelectorAll('.compare-column');
    return Array.from(cols).map(col => ({
      label: col.querySelector('.compare-column-header')?.textContent || '',
      content: col.querySelector('.compare-content')?.textContent?.substring(0, 200) || '',
      blocked: !!col.querySelector('.blocked-warning'),
      loading: !!col.querySelector('.compare-loading'),
    }));
  });
  for (const col of columns) {
    console.log(`  ${col.label}: ${col.blocked ? 'BLOCKED' : col.loading ? 'LOADING' : col.content.substring(0, 100)}`);
  }

  // Summary
  console.log('\n=== SUMMARY ===');
  for (const r of results) {
    console.log(`  ${r.id}. ${r.name}: ${r.verdict}`);
  }
  console.log(`\nConsole errors: ${errors.length ? errors.join('; ') : 'None'}`);

  await browser.close();
})().catch(err => { console.error('FATAL:', err.message); process.exit(1); });
