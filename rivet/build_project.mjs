// Builds rivet/xp_monthly_letter.rivet-project from the prompts in rivet/prompts/.
//
// The graphs are described below as data (inputs -> LLM steps -> outputs) and serialized with
// Rivet's own serializer, so the file opens in the Rivet app like any hand-made project.
// Prompts live in plain Markdown files, which keeps them reviewable in git.
//
//   node rivet/build_project.mjs

import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { globalRivetNodeRegistry, serializeProject } from '@ironclad/rivet-core';

const HERE = dirname(fileURLToPath(import.meta.url));
const prompt = (name) => readFileSync(join(HERE, 'prompts', `${name}.md`), 'utf8').trim();

// Each step is a Prompt node feeding a Chat node, whose model comes from the graph input
// named in `model` (default "model"). `vars` maps every {{variable}} of the prompt
// to a graph input ("input:<id>") or to the response of an earlier step ("step:<id>").
// Roles in the letter graph: the Analyst agent relates the figures to the client's profile and the
// macro scenario; the Writer agent only turns that analysis into the letter, following its rules;
// the Reviewer checks suitability and tone before the code checks every figure.
const GRAPHS = [
  {
    id: 'macro_digest',
    name: '1. Macro digest (once per month)',
    description: 'Digests the XP macro research once per month; the result is reused for every client.',
    inputs: ['macro_text', 'letter_date', 'model'],
    steps: [
      { id: 'macro_digest', vars: { macro_text: 'input:macro_text', letter_date: 'input:letter_date' }, temperature: 0.1, maxTokens: 1500 },
    ],
    outputs: { macro_digest: 'macro_digest' },
  },
  {
    id: 'monthly_letter',
    name: '2. Monthly letter (per client)',
    description: 'Profile, performance analysis, suggestions, letter and critic for one client. Every figure comes from the Python engine.',
    inputs: ['client', 'profile_label', 'risk_profile_text', 'portfolio_text', 'profitability', 'portfolio_facts',
             'suggestion_candidates', 'macro_digest', 'revision_notes', 'model', 'writer_model'],
    steps: [
      { id: 'profile_summary', role: 'Analyst', vars: { profile_label: 'input:profile_label', risk_profile_text: 'input:risk_profile_text' },
        temperature: 0.1, maxTokens: 800 },
      { id: 'performance_analysis', role: 'Analyst', vars: { client: 'input:client', portfolio_text: 'input:portfolio_text', profitability: 'input:profitability',
          macro_digest: 'input:macro_digest' },
        temperature: 0.2, maxTokens: 1200 },
      { id: 'recommendations', role: 'Analyst', vars: { profile_summary: 'step:profile_summary', macro_digest: 'input:macro_digest',
          performance_analysis: 'step:performance_analysis', portfolio_facts: 'input:portfolio_facts',
          suggestion_candidates: 'input:suggestion_candidates', revision_notes: 'input:revision_notes' },
        temperature: 0.3, maxTokens: 1200 },
      { id: 'letter_writer', role: 'Writer', vars: { client: 'input:client', profile_summary: 'step:profile_summary',
          performance_analysis: 'step:performance_analysis', macro_digest: 'input:macro_digest',
          recommendations: 'step:recommendations', revision_notes: 'input:revision_notes' },
        temperature: 0.4, maxTokens: 2500, model: 'writer_model' },
      { id: 'critic', role: 'Reviewer', vars: { client: 'input:client', profile_summary: 'step:profile_summary',
          profitability: 'input:profitability', portfolio_facts: 'input:portfolio_facts', macro_digest: 'input:macro_digest', letter: 'step:letter_writer' },
        temperature: 0, maxTokens: 1200, model: 'writer_model' },
    ],
    outputs: { profile_summary: 'profile_summary', performance_analysis: 'performance_analysis',
               recommendations: 'recommendations', letter: 'letter_writer', critic: 'critic' },
  },
  {
    id: 'portfolio_extraction',
    name: '3. Statement extraction (fallback)',
    description: 'Used only when the code reader does not recognise a statement; the result goes through the same sum checks.',
    inputs: ['statement_text', 'model'],
    steps: [
      { id: 'portfolio_extraction', vars: { statement_text: 'input:statement_text' }, temperature: 0, maxTokens: 4000 },
    ],
    outputs: { portfolio_json: 'portfolio_extraction' },
  },
];

function makeNode(type, title, data, x, y, width = 280) {
  const n = globalRivetNodeRegistry.createDynamic(type);
  n.id = `${title}`.replace(/[^A-Za-z0-9_-]/g, '_');
  n.title = title;
  n.data = { ...n.data, ...data };
  n.visualData = { x, y, width };
  return n;
}

function buildGraph(spec) {
  // Node ids are unique across the whole project.
  const node = (type, title, data, x, y, width) => {
    const n = makeNode(type, title, data, x, y, width);
    n.id = `${spec.id}__${n.id}`;
    return n;
  };
  const nodes = [];
  const connections = [];
  const link = (from, outputId, to, inputId) =>
    connections.push({ outputNodeId: from.id, outputId, inputNodeId: to.id, inputId });

  const inputs = {};
  spec.inputs.forEach((id, i) => {
    inputs[id] = node('graphInput', `in_${id}`, { id, dataType: 'string', useDefaultValueInput: false, defaultValue: '' }, 0, i * 160);
    nodes.push(inputs[id]);
  });

  const system = node('prompt', `${spec.id}_system`, { type: 'system', promptText: prompt('system') }, 400, -400, 320);
  nodes.push(system);

  const chats = {};
  spec.steps.forEach((step, i) => {
    const x = 450 + i * 700;
    const label = step.role ? `${step.role}: ${step.id}` : step.id;
    const p = node('prompt', `${label} (prompt)`, { type: 'user', promptText: prompt(step.id) }, x, 200 + (i % 2) * 120, 320);
    const c = node('chat', `${label} (LLM)`, {
      temperature: step.temperature, maxTokens: step.maxTokens, useModelInput: true,
      responseFormat: 'json', cache: false, useAsGraphPartialOutput: false,
    }, x + 360, 200 + (i % 2) * 120, 240);
    nodes.push(p, c);
    for (const [variable, source] of Object.entries(step.vars)) {
      const [kind, id] = source.split(':');
      if (kind === 'input') link(inputs[id], 'data', p, variable);
      else link(chats[id], 'response', p, variable);
    }
    link(p, 'output', c, 'prompt');
    link(system, 'output', c, 'systemPrompt');
    link(inputs[step.model ?? 'model'], 'data', c, 'model');
    chats[step.id] = c;
  });

  Object.entries(spec.outputs).forEach(([id, stepId], i) => {
    const out = node('graphOutput', `out_${id}`, { id, dataType: 'string' }, 450 + spec.steps.length * 700, i * 160);
    nodes.push(out);
    link(chats[stepId], 'response', out, 'value');
  });

  return { metadata: { id: spec.id, name: spec.name, description: spec.description }, nodes, connections };
}

const project = {
  metadata: {
    id: 'xp_monthly_letter',
    title: 'XP Monthly Letter',
    description: 'Rivet decides, Python executes: analysis, suggestions and the letter are written here; '
      + 'figures, charts, PDF and e-mail are produced by the Python platform.',
    mainGraphId: 'monthly_letter',
  },
  graphs: Object.fromEntries(GRAPHS.map((g) => [g.id, buildGraph(g)])),
  plugins: [],
};

const out = join(HERE, 'xp_monthly_letter.rivet-project');
writeFileSync(out, serializeProject(project, {}));
console.log(`written ${out}`);
