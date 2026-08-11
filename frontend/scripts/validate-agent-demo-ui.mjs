import { readFileSync, statSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptFile = fileURLToPath(import.meta.url);
const scriptDir = dirname(scriptFile);
const frontendRoot = resolve(scriptDir, '..');
const repoRoot = resolve(frontendRoot, '..');
const paths = {
  scope: resolve(repoRoot, 'docs', 'agent', 'agent-demo-ui-scope.md'),
  types: resolve(frontendRoot, 'src', 'api', 'types.ts'),
  client: resolve(frontendRoot, 'src', 'api', 'client.ts'),
  page: resolve(frontendRoot, 'src', 'pages', 'AgentRuns.tsx'),
  app: resolve(frontendRoot, 'src', 'App.tsx'),
  layout: resolve(frontendRoot, 'src', 'components', 'Layout.tsx'),
  styles: resolve(frontendRoot, 'src', 'styles', 'global.css'),
};

function assertExists(path) {
  statSync(path);
}

function assertContains(text, needle) {
  if (!text.includes(needle)) {
    throw new Error(`Missing expected text: ${needle}`);
  }
}

function assertNotContains(text, needle) {
  if (text.includes(needle)) {
    throw new Error(`Unexpected text present: ${needle}`);
  }
}

function main() {
  Object.values(paths).forEach(assertExists);
  const scope = readFileSync(paths.scope, 'utf8');
  const types = readFileSync(paths.types, 'utf8');
  const client = readFileSync(paths.client, 'utf8');
  const page = readFileSync(paths.page, 'utf8');
  const app = readFileSync(paths.app, 'utf8');
  const layout = readFileSync(paths.layout, 'utf8');
  const styles = readFileSync(paths.styles, 'utf8');

  assertContains(scope, '## 2. In Scope');
  assertContains(scope, '## 3. Non-goals');
  assertContains(scope, 'no multi-agent collaboration');
  assertContains(scope, 'no LangGraph takeover');

  [
    'export type AgentRunStatus',
    'export interface AgentTriageResult',
    'export interface AgentRunState',
    'export interface AgentToolCall',
    'export interface AgentStep',
    'export interface AgentRun',
    'export interface AgentRunResumePayload',
  ].forEach((token) => assertContains(types, token));

  [
    "fetchJson<AgentRun>('/agent/runs'",
    'getAgentRun:',
    'resumeAgentRun:',
    'cancelAgentRun:',
  ].forEach((token) => assertContains(client, token));

  [
    'Start / Reuse Agent Run',
    'Human Gate · Confirm Triage',
    'Human Gate · Clarification Required',
    'Human Gate · Final Review',
    'CONTROLLED_SUBTYPES',
    'Execution Timeline',
    'Controlled Agent state · sensitive fields hidden',
    'redactForUi',
    "'[hidden from UI]'",
    "'[redacted]'",
    'api.resumeAgentRun',
    'api.cancelAgentRun',
    'api.submitAnalysisFeedback',
    "setFeedbackAction('accepted')",
    "setFeedbackNote('')",
    "setEditedOutput('')",
    'run?.analysis_log_id',
  ].forEach((token) => assertContains(page, token));

  assertContains(app, '<Route path="/agent-runs" element={<AgentRuns />} />');
  assertContains(layout, "{ to: '/agent-runs', label: 'Agent Investigation' }");
  assertContains(styles, '.agent-timeline');
  assertContains(styles, '.agent-status-waiting');

  const publicSurface = [types, client, page, app, layout, styles].join('\n');
  assertNotContains(publicSurface, 'API_LLM_API_KEY');
  assertNotContains(publicSurface, 'EMBEDDING_API_KEY');
  assertNotContains(publicSurface, 'Bearer token');
  assertNotContains(publicSurface, 'sk-');

  console.log('Frontend Agent demo UI assertions passed');
}

main();
