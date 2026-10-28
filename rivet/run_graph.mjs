// Runs one graph of xp_monthly_letter.rivet-project and prints its outputs as JSON.
// Called by core/letter_ai.py; the OpenAI key comes from the OPENAI_API_KEY environment variable.
//
//   node rivet/run_graph.mjs <graph id> <inputs.json>
//
// Optional: OPENAI_ENDPOINT points the chat nodes to another OpenAI-compatible endpoint (tests).

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { runGraphInFile } from '@ironclad/rivet-node';

const HERE = dirname(fileURLToPath(import.meta.url));
const [graph, inputsPath] = process.argv.slice(2);
if (!graph || !inputsPath) {
  console.error('usage: node rivet/run_graph.mjs <graph id> <inputs.json>');
  process.exit(2);
}
if (!process.env.OPENAI_API_KEY) {
  console.error('OPENAI_API_KEY is not set (see .env.example)');
  process.exit(2);
}

const inputs = JSON.parse(readFileSync(inputsPath, 'utf8'));
const usage = { requestTokens: 0, responseTokens: 0, cost: 0 };

const outputs = await runGraphInFile(join(HERE, 'xp_monthly_letter.rivet-project'), {
  graph,
  inputs: Object.fromEntries(Object.entries(inputs).map(([k, v]) => [k, { type: 'string', value: String(v) }])),
  openAiKey: process.env.OPENAI_API_KEY,
  openAiOrganization: process.env.OPENAI_ORG_ID,
  openAiEndpoint: process.env.OPENAI_ENDPOINT,
  onNodeFinish: ({ outputs: nodeOutputs }) => {
    usage.requestTokens += nodeOutputs?.requestTokens?.value ?? 0;
    usage.responseTokens += nodeOutputs?.responseTokens?.value ?? 0;
    usage.cost += nodeOutputs?.cost?.value ?? 0;
  },
});

const result = Object.fromEntries(
  Object.entries(outputs).filter(([k]) => k !== 'cost').map(([k, v]) => [k, v?.value ?? null]));
process.stdout.write(JSON.stringify({ outputs: result, usage }));
