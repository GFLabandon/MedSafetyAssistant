import { expect, test } from '@playwright/test';


function responseFor(question) {
  const base = {
    resolution: {
      schema_version: 'entity-resolution-v1',
      status: 'resolved',
      medications: [],
      contexts: [],
      entities: [],
      unresolved_mentions: [],
      clarification_question: null,
      safety_flags: [],
    },
    explanation: {
      conclusion_status: 'no_known_risk_in_scope',
      summary: '当前来源对齐目录内未命中已收录风险；这不代表该药品安全。',
      claims: [],
      limitations: ['当前覆盖范围有限。'],
      resolved_medications: [],
      unresolved_inputs: [],
      resolved_contexts: [],
      unresolved_contexts: [],
      missing_context: [],
      data_version: 'v1.0.0-alpha.3',
      generation_mode: 'deterministic',
      prompt_version: 'evidence-order-v2',
      fallback_reason: null,
    },
    trace: {
      schema_version: 'request-trace-v1',
      request_id: 'e2e-request-001',
      total_duration_ms: 1.5,
      stages: [
        { name: 'entity_resolution', status: 'completed', duration_ms: 0.2 },
        { name: 'safety_engine', status: 'completed', duration_ms: 0.3 },
        { name: 'evidence_explanation', status: 'completed', duration_ms: 0.4 },
      ],
      resolution_status: 'resolved',
      conclusion_status: 'no_known_risk_in_scope',
    },
  };

  if (question.includes('泰诺')) {
    base.resolution.medications = ['泰诺', '感康'];
    base.explanation.conclusion_status = 'risk_found';
    base.explanation.summary = '在当前来源对齐数据范围内发现 1 条需要关注的用药风险。';
    base.explanation.claims = [{
      fact_id: 'fact-duplicate-acetaminophen-001',
      risk_type: 'DUPLICATE_THERAPY',
      severity: 'RED',
      statement: '两个产品都含对乙酰氨基酚。',
      severity_rationale: '项目风险沟通等级，不是临床分级。',
      source_ids: ['source-fda-acetaminophen-2025'],
      source_locator: 'Safe Use of Acetaminophen，第108至116行。',
      label_status: 'source_aligned',
    }];
    base.trace.conclusion_status = 'risk_found';
    return base;
  }

  if (question.includes('阿司匹林')) {
    base.resolution.status = 'needs_clarification';
    base.resolution.medications = ['布洛芬', '阿司匹林'];
    base.resolution.clarification_question = '请补充以下判断条件：阿司匹林用于心血管保护。';
    base.explanation.conclusion_status = 'insufficient_information';
    base.explanation.summary = '现有信息不足，系统未作完整风险判断。';
    base.trace.resolution_status = 'needs_clarification';
    base.trace.conclusion_status = 'insufficient_information';
    return base;
  }

  if (question.includes('知识库')) {
    base.resolution.medications = ['泰诺'];
    base.explanation.conclusion_status = 'knowledge_unavailable';
    base.explanation.summary = '用药安全知识库当前不可用，系统未进行风险判断，请稍后重试。';
    base.explanation.data_version = null;
    base.trace.conclusion_status = 'knowledge_unavailable';
    base.trace.stages[1].status = 'degraded';
    return base;
  }

  base.resolution.status = 'unknown';
  base.resolution.unresolved_mentions = ['星云片'];
  base.resolution.clarification_question = '未识别到当前 V1 目录中的药品，请提供具体商品名或成分名。';
  base.explanation.conclusion_status = 'out_of_scope';
  base.explanation.summary = '部分或全部输入超出当前来源对齐目录。';
  base.trace.resolution_status = 'unknown';
  base.trace.conclusion_status = 'out_of_scope';
  base.trace.stages[1].status = 'skipped';
  return base;
}


test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/query', async (route) => {
    const payload = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(responseFor(payload.question)),
    });
  });
  await page.goto('/');
});


async function submit(page, question) {
  await page.getByPlaceholder('请输入具体药品，例如：泰诺和感康能一起吃吗？').fill(question);
  await page.getByRole('button', { name: '开始分析' }).click();
}


test('renders a source-aligned risk with traceable evidence', async ({ page }) => {
  await submit(page, '泰诺和感康能一起吃吗？');

  await expect(page.getByRole('heading', { name: '发现已收录风险' })).toBeVisible();
  await expect(page.getByText('fact-duplicate-acetaminophen-001')).toBeVisible();
  await expect(page.getByText('source-fda-acetaminophen-2025')).toBeVisible();
  await expect(page.getByText('e2e-request-001')).toBeVisible();
});


test('asks for required context without showing a risk claim', async ({ page }) => {
  await submit(page, '布洛芬和阿司匹林能一起吃吗？');

  await expect(page.getByRole('heading', { name: '需要补充信息' })).toBeVisible();
  await expect(page.getByText('请补充以下判断条件：阿司匹林用于心血管保护。')).toBeVisible();
  await expect(page.locator('.evidence-claim')).toHaveCount(0);
});


test('keeps an unknown medication out of scope', async ({ page }) => {
  await submit(page, '星云片');

  await expect(page.getByRole('heading', { name: '超出当前覆盖范围' })).toBeVisible();
  await expect(page.locator('.tag').getByText('星云片', { exact: true })).toBeVisible();
  await expect(page.locator('.evidence-claim')).toHaveCount(0);
});


test('never renders dependency failure as no known risk', async ({ page }) => {
  await submit(page, '模拟知识库故障');

  await expect(page.getByRole('heading', { name: '知识服务不可用' })).toBeVisible();
  await expect(page.getByText('knowledge_unavailable', { exact: true })).toBeVisible();
  await expect(page.getByText('当前范围内未命中风险')).toHaveCount(0);
});
