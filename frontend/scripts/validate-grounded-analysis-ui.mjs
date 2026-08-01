import { readFileSync, statSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptFile = fileURLToPath(import.meta.url);
const scriptDir = dirname(scriptFile);
const frontendRoot = resolve(scriptDir, '..');
const paths = {
  types: resolve(frontendRoot, 'src', 'api', 'types.ts'),
  issues: resolve(frontendRoot, 'src', 'pages', 'Issues.tsx'),
  styles: resolve(frontendRoot, 'src', 'styles', 'global.css'),
  validator: resolve(frontendRoot, 'scripts', 'validate-grounded-analysis-ui.mjs'),
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

  const types = readFileSync(paths.types, 'utf8');
  assertContains(types, 'export type RetrievalStatus');
  assertContains(types, 'export interface KnowledgeCitation');
  assertContains(types, 'export interface GroundedAnalysisFields');
  assertContains(types, 'retrieval_status: RetrievalStatus');
  assertContains(types, 'knowledge_citations: KnowledgeCitation[]');
  assertContains(types, 'retrieval_error_code?: string | null;');
  assertContains(types, 'knowledge_grounded: boolean;');
  assertContains(types, 'export interface AIAnalysisHistoryItem extends IssueAnalysisResult {}');

  const issues = readFileSync(paths.issues, 'utf8');
  assertContains(issues, 'formatSimilarityScore');
  assertContains(issues, 'Number.isFinite');
  assertContains(issues, 'getGroundingPresentation');
  assertContains(issues, 'renderGroundingEvidence');
  assertContains(issues, 'Grounded with Knowledge');
  assertContains(issues, 'Knowledge Retrieved · Not Grounded');
  assertContains(issues, 'No Knowledge Match');
  assertContains(issues, 'Retrieval Failed');
  assertContains(issues, 'Retrieval Not Attempted');
  assertContains(issues, 'Knowledge Citations');
  const renderCount = (issues.match(/renderGroundingEvidence/g) || []).length;
  if (renderCount < 3) {
    throw new Error(`Expected renderGroundingEvidence at least 3 times, found ${renderCount}`);
  }
  assertContains(issues, 'setCurrentAnalysis(item)');
  assertContains(issues, 'setCurrentAnalysis(matched)');
  assertNotContains(issues, 'retrieval_query');
  assertNotContains(issues, 'chunk_text');
  assertNotContains(issues, 'source_uri');

  const css = readFileSync(paths.styles, 'utf8');
  [
    '.grounding-panel',
    '.grounding-header',
    '.grounding-status',
    '.grounding-badge',
    '.grounding-badge-grounded',
    '.grounding-badge-retrieved',
    '.grounding-badge-empty',
    '.grounding-badge-failed',
    '.grounding-badge-neutral',
    '.grounding-meta',
    '.grounding-error',
    '.grounding-details',
    '.grounding-empty',
    '.citation-list',
    '.citation-card',
    '.citation-card-header',
    '.citation-id',
    '.citation-title',
    '.citation-meta',
  ].forEach((token) => assertContains(css, token));

  const sensitiveScan = [types, issues, css].join('\n');
  assertNotContains(sensitiveScan, 'sk-');
  assertNotContains(sensitiveScan, 'Bearer token');
  assertNotContains(sensitiveScan, 'Workspace');
  assertNotContains(sensitiveScan, 'API_LLM_API_KEY');
  assertNotContains(sensitiveScan, 'EMBEDDING_API_KEY');
  assertNotContains(sensitiveScan, 'ap-southeast-1.maas');

  console.log('Frontend Grounded analysis UI assertions passed');
}

main();
