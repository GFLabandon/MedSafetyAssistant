import { expect, test } from '@playwright/test';


function responseFor(question) {
  const base = {
    feedback_id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    session_context: {
      schema_version: 'session-context-trace-v1',
      read_status: 'empty',
      write_status: 'stored',
      context_applied: false,
    },
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
      data_version: 'v1.0.0-alpha.4',
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

  if (question.includes('刚才的药')) {
    base.session_context.read_status = 'available';
    base.session_context.context_applied = true;
    base.resolution.medications = ['泰诺', '感康'];
    base.explanation.conclusion_status = 'risk_found';
    base.explanation.summary = '在当前来源对齐数据范围内发现 1 条需要关注的用药风险。';
    base.trace.conclusion_status = 'risk_found';
    return base;
  }

  if (question.includes('XYZ123')) {
    base.session_context.write_status = 'skipped';
    base.resolution.status = 'ambiguous';
    base.resolution.medications = ['泰诺'];
    base.resolution.unresolved_mentions = ['XYZ123'];
    base.resolution.clarification_question = '请确认与已识别药品并列的另一项，并提供包装上的具体商品名或成分名。';
    base.explanation.conclusion_status = 'insufficient_information';
    base.explanation.summary = '现有信息不足，系统未作完整风险判断。';
    base.trace.resolution_status = 'ambiguous';
    base.trace.conclusion_status = 'insufficient_information';
    base.trace.stages[1].status = 'skipped';
    return base;
  }

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
    base.sources = [{
      source_id: 'source-fda-acetaminophen-2025',
      title: 'Acetaminophen',
      publisher: 'U.S. Food and Drug Administration',
      version: 'Content current as of 2025-08-14',
      url: 'https://www.fda.gov/drugs/safe-use-over-counter-pain-relievers-and-fever-reducers/acetaminophen',
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
  await page.route('**/api/v1/query/session', async (route) => {
    const payload = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(responseFor(payload.question)),
    });
  });
  await page.route('**/api/v1/knowledge/search', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        schema_version: 'reviewed-fact-search-v1',
        data_version: 'v1.0.0-alpha.4',
        retrieval_method: 'character-bigram-over-reviewed-summaries',
        hits: [{
          fact_id: 'fact-interaction-ibuprofen-aspirin-cardioprotection-001',
          summary: '布洛芬可能削弱阿司匹林的抗血小板作用。',
          source_locator: 'FDA Science Paper 第1页',
          sources: [{ source_id: 'source-fda-ibuprofen-aspirin-2006', title: 'FDA Science Paper', url: 'https://www.fda.gov/media/76636/download' }],
          score: 12,
        }],
      }),
    });
  });
  await page.route('**/api/v1/source-documents/search', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        schema_version: 'project-document-search-v1',
        corpus: 'reviewed_source_excerpt',
        method: 'lexical',
        hits: [{
          chunk_id: 'source-fda-acetaminophen-safe-use-2026-09-24:001',
          document_id: 'source-fda-acetaminophen-safe-use-2026-09-24',
          title: 'Safe Use of Acetaminophen',
          heading: 'Safe Use of Acetaminophen',
          text: 'Do not use more than one acetaminophen-containing product at a time.',
          source_id: 'source-fda-acetaminophen-2025',
          source_url: 'https://www.fda.gov/drugs/safe-use-over-counter-pain-relievers-and-fever-reducers/acetaminophen#safeuse',
          linked_fact_ids: ['fact-duplicate-acetaminophen-001'],
          score: 1,
        }],
      }),
    });
  });
  await page.route('**/api/v1/documents/search', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        schema_version: 'project-document-search-v1',
        corpus: 'project_documentation',
        method: route.request().postDataJSON().method,
        vectorizer_id: null,
        hits: [{
          chunk_id: 'project-safety-boundary:001',
          document_id: 'project-safety-boundary',
          title: '项目安全边界',
          heading: '系统用途',
          text: '本项目是家庭常见用药风险筛查的工程演示系统。',
          score: 3,
        }],
      }),
    });
  });
  await page.route('**/api/v1/feedback', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'recorded' }),
    });
  });
  await page.goto('/');
});

test('keeps one explicit session for a pronoun follow-up', async ({ page }) => {
  const sessions = [];
  page.on('request', (request) => {
    if (request.url().endsWith('/api/v1/query/session')) {
      sessions.push(request.postDataJSON().session_id);
    }
  });
  await submit(page, '泰诺和感康能一起吃吗？');
  await expect(page.getByText(/会话上下文：已保存已识别药品/)).toBeVisible();
  await submit(page, '刚才的药还能一起吃吗？');
  await expect(page.getByText(/本次已使用上一次识别的药品/)).toBeVisible();
  expect(sessions).toHaveLength(2);
  expect(sessions[0]).toBe(sessions[1]);
});

test('searches reviewed facts without changing the risk response', async ({ page }) => {
  await page.getByRole('textbox', { name: '检索已审事实' }).fill('布洛芬和阿司匹林');
  await page.getByRole('button', { name: '检索', exact: true }).click();

  await expect(page.getByText('布洛芬可能削弱阿司匹林的抗血小板作用。')).toBeVisible();
  await expect(page.getByRole('link', { name: 'FDA Science Paper' })).toHaveAttribute('href', /fda\.gov/);
  await expect(page.getByRole('heading', { name: '发现已收录风险' })).toHaveCount(0);
});

test('shows the reviewed FDA source excerpt separately from the risk response', async ({ page }) => {
  await page.getByRole('combobox', { name: '检索范围' }).selectOption('sources');
  await page.getByRole('textbox', { name: '检索已审事实' }).fill('对乙酰氨基酚重复成分');
  await page.getByRole('button', { name: '检索', exact: true }).click();

  await expect(page.getByText('Do not use more than one acetaminophen-containing product at a time.')).toBeVisible();
  await expect(page.getByRole('link', { name: '打开 FDA 原页面' })).toHaveAttribute('href', /fda\.gov/);
  await expect(page.getByRole('heading', { name: '发现已收录风险' })).toHaveCount(0);
});

test('searches project documents as a separate experiment', async ({ page }) => {
  await page.getByRole('textbox', { name: '检索项目文档' }).fill('系统用途');
  await page.getByRole('combobox', { name: '文档检索方法' }).selectOption('hashing_vector');
  await page.getByRole('button', { name: '检索文档' }).click();

  await expect(page.getByText('本项目是家庭常见用药风险筛查的工程演示系统。')).toBeVisible();
  await expect(page.getByText('方法：hashing_vector · 命中 1 个片段')).toBeVisible();
  await expect(page.getByRole('heading', { name: '发现已收录风险' })).toHaveCount(0);
});

test('submits structured feedback after a query', async ({ page }) => {
  await submit(page, '泰诺和感康能一起吃吗？');
  await page.getByRole('button', { name: '需改进' }).click();
  await page.getByRole('combobox', { name: '需改进原因' }).selectOption('missing_evidence');
  await page.getByRole('button', { name: '提交反馈' }).click();
  await expect(page.getByText('感谢反馈，已记录。')).toBeVisible();
});


async function submit(page, question) {
  await page.getByPlaceholder('请输入具体药品，例如：泰诺和感康能一起吃吗？').fill(question);
  await page.getByRole('button', { name: '开始分析' }).click();
}


test('renders a source-aligned risk with traceable evidence', async ({ page }) => {
  await submit(page, '泰诺和感康能一起吃吗？');

  await expect(page.getByRole('heading', { name: '发现已收录风险' })).toBeVisible();
  await expect(page.getByText('fact-duplicate-acetaminophen-001')).toBeVisible();
  await expect(page.getByText('source-fda-acetaminophen-2025').first()).toBeVisible();
  await expect(page.getByRole('link', { name: 'Acetaminophen' })).toHaveAttribute('href', /fda\.gov/);
  await expect(page.getByText('e2e-request-001')).toBeVisible();
});


test('asks for required context without showing a risk claim', async ({ page }) => {
  await submit(page, '布洛芬和阿司匹林能一起吃吗？');

  await expect(page.getByRole('heading', { name: '需要补充信息' })).toBeVisible();
  await expect(page.getByText('请补充以下判断条件：阿司匹林用于心血管保护。')).toBeVisible();
  await expect(page.locator('.evidence-claim')).toHaveCount(0);
});


test('shows unmatched pair operand as clarification without retaining session context', async ({ page }) => {
  await submit(page, '泰诺能和XYZ123一起吃吗？');

  await expect(page.getByRole('heading', { name: '需要补充信息' })).toBeVisible();
  await expect(page.getByText('请确认与已识别药品并列的另一项，并提供包装上的具体商品名或成分名。')).toBeVisible();
  await expect(page.locator('.tag').getByText('XYZ123', { exact: true })).toBeVisible();
  await expect(page.locator('.evidence-claim')).toHaveCount(0);
  await expect(page.getByText(/会话上下文：未保存/)).toBeVisible();
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
