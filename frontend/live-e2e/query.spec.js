import { expect, test } from '@playwright/test';


async function submit(page, question) {
  await page.getByPlaceholder('请输入具体药品，例如：泰诺和感康能一起吃吗？').fill(question);
  await page.getByRole('button', { name: '开始分析' }).click();
}


test('renders a real API risk response and then a clarification without stale evidence', async ({ page }) => {
  await page.goto('/');
  const riskResponse = page.waitForResponse((response) =>
    response.url().endsWith('/api/v1/query/session')
  );
  await submit(page, '泰诺和感康能一起吃吗？');
  const riskHttp = await riskResponse;

  expect(riskHttp.status()).toBe(200);
  expect(riskHttp.url()).toContain('127.0.0.1:8000');
  expect(riskHttp.headers()['access-control-allow-origin']).toBe('http://127.0.0.1:4173');

  await expect(page.getByRole('heading', { name: '发现已收录风险' })).toBeVisible();
  await expect(page.getByText('fact-duplicate-acetaminophen-001')).toBeVisible();
  await expect(page.getByRole('link', { name: /Acetaminophen/ }).first()).toHaveAttribute('href', /fda\.gov/);

  const clarificationResponse = page.waitForResponse((response) =>
    response.url().endsWith('/api/v1/query/session')
  );
  await submit(page, '泰诺能和XYZ123一起吃吗？');
  expect((await clarificationResponse).status()).toBe(200);

  await expect(page.getByRole('heading', { name: '需要补充信息' })).toBeVisible();
  await expect(page.locator('.tag').getByText('XYZ123', { exact: true })).toBeVisible();
  await expect(page.locator('.evidence-claim')).toHaveCount(0);
  await expect(page.getByText(/会话上下文：未保存/)).toBeVisible();
});
