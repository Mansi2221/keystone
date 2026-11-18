const { chromium } = require('/Users/mansi/keystone/ui-web/node_modules/playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const errors = [];
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
  page.on('pageerror', err => errors.push(err.message));

  // Load and wait for auto-login as CEO
  await page.goto('http://localhost:5173');
  await page.waitForSelector('.identity-card', { timeout: 10000 });
  await page.waitForTimeout(1500);

  // Ask a simple question
  console.log('Sending: What is my salary?');
  await page.fill('.chat-input', 'What is my salary?');
  await page.click('.send-btn');

  // Wait up to 3 minutes
  try {
    await page.waitForFunction(() => {
      const bubbles = document.querySelectorAll('.chat-bubble.assistant .bubble-content');
      const last = bubbles[bubbles.length - 1];
      return last && last.textContent && last.textContent.length > 30;
    }, { timeout: 180000 });
    await page.waitForTimeout(1500);
    console.log('Got response!');
  } catch (e) {
    console.log('Timed out after 3 min');
  }
  await page.screenshot({ path: 'docs/media/02-ceo-salary.png' });

  // Get response preview
  const content = await page.evaluate(() => {
    const bubbles = document.querySelectorAll('.chat-bubble.assistant .bubble-content');
    const last = bubbles[bubbles.length - 1];
    return last ? last.textContent.substring(0, 300) : 'NO CONTENT';
  });
  console.log('Response:', content);

  // Count UI elements
  const stepCount = await page.evaluate(() => document.querySelectorAll('.tool-step').length);
  const sourceCount = await page.evaluate(() => document.querySelectorAll('.source-pill').length);
  const traceLink = await page.evaluate(() => {
    const link = document.querySelector('.trace-link');
    return link ? link.textContent : 'none';
  });
  console.log('Tool steps:', stepCount, '| Sources:', sourceCount, '| Trace:', traceLink);
  console.log('Console errors:', errors.length ? errors.join('; ') : 'None');

  // --- Now switch to manager and ask about salaries ---
  console.log('\n--- Switching to Sales Manager ---');
  await page.locator('.user-card', { hasText: 'Sales Manager' }).click();
  await page.waitForTimeout(2500);
  await page.fill('.chat-input', 'Show me the salaries of my direct reports');
  await page.click('.send-btn');
  try {
    await page.waitForFunction(() => {
      const bubbles = document.querySelectorAll('.chat-bubble.assistant .bubble-content');
      const last = bubbles[bubbles.length - 1];
      return last && last.textContent && last.textContent.length > 30;
    }, { timeout: 180000 });
    await page.waitForTimeout(1500);
    console.log('Got manager response!');
  } catch (e) {
    console.log('Manager query timed out');
  }
  await page.screenshot({ path: 'docs/media/03-manager-salaries.png' });
  const mgrContent = await page.evaluate(() => {
    const bubbles = document.querySelectorAll('.chat-bubble.assistant .bubble-content');
    const last = bubbles[bubbles.length - 1];
    return last ? last.textContent.substring(0, 300) : 'NO CONTENT';
  });
  console.log('Manager response:', mgrContent);

  // --- Contractor aggregation trap ---
  console.log('\n--- Switching to Contractor ---');
  await page.locator('.user-card', { hasText: 'Contract Developer' }).click();
  await page.waitForTimeout(2500);
  await page.fill('.chat-input', 'What is the average salary in the Engineering department?');
  await page.click('.send-btn');
  try {
    await page.waitForFunction(() => {
      const bubbles = document.querySelectorAll('.chat-bubble.assistant .bubble-content');
      const last = bubbles[bubbles.length - 1];
      return last && last.textContent && last.textContent.length > 20;
    }, { timeout: 180000 });
    await page.waitForTimeout(1500);
    console.log('Got contractor response!');
  } catch (e) {
    console.log('Contractor query timed out');
  }
  await page.screenshot({ path: 'docs/media/04-aggregation-trap.png' });
  const ctrContent = await page.evaluate(() => {
    const bubbles = document.querySelectorAll('.chat-bubble.assistant .bubble-content');
    const last = bubbles[bubbles.length - 1];
    return last ? last.textContent.substring(0, 300) : 'NO CONTENT';
  });
  console.log('Contractor response:', ctrContent);

  console.log('\nAll screenshots saved. Errors:', errors.length ? errors.join('; ') : 'None');
  await browser.close();
})().catch(err => { console.error('FATAL:', err.message); process.exit(1); });
