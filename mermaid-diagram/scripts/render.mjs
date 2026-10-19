#!/usr/bin/env node
// Render a Mermaid diagram to a PNG sized for a phone, for a Hermes Agent reply.
//
//   node render.mjs /tmp/diagram.mmd        (or pipe the Mermaid text on stdin)
//
// Success: prints `MEDIA:<absolute png path>` and a size line, exits 0.
// Bad Mermaid: prints the line, column and reason to stderr, exits 2.
// Dependencies missing: prints the one-time install command to stderr, exits 3.
//
// Pele (Obsidian's Mermaid renderer) lays the diagram out in plain Node, with no
// browser, and resvg turns the SVG into a PNG.
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomBytes } from 'node:crypto';

const HERMES_HOME = process.env.HERMES_HOME || join(homedir(), '.hermes');
// Outside the skill folder, so `hermes skills update` or a sync does not delete them.
const DEPS = process.env.MERMAID_DIAGRAM_DEPS || join(HERMES_HOME, 'tools/mermaid-diagram');
// The gateway always trusts this folder as a source for MEDIA: delivery.
const OUT_DIR = process.env.MERMAID_DIAGRAM_OUT || join(HERMES_HOME, 'cache/images');
// Pele measures text with Arial's widths when there is no browser canvas, and Liberation
// Sans shares Arial's metrics, so labels fit their boxes. DejaVu Sans covers anything missing.
const FONT = 'Liberation Sans, DejaVu Sans, sans-serif';
// Below Pele's 640px breakpoint, so a wide left-to-right flowchart turns top-to-bottom.
const PHONE_WIDTH = 480;
// Telegram rejects a photo whose width + height exceeds 10000 px.
const MAX_SIDE_SUM = 9000;

if (!existsSync(join(DEPS, 'node_modules/pele'))) {
  const here = dirname(fileURLToPath(import.meta.url));
  console.error(`mermaid-diagram: dependencies are not installed at ${DEPS}. Install once with:\n` +
    `mkdir -p ${DEPS} && cp ${here}/package.json ${here}/package-lock.json ${DEPS}/ && npm ci --ignore-scripts --prefix ${DEPS}`);
  process.exit(3);
}
const require = createRequire(join(DEPS, 'package.json'));
const { render, PeleError } = await import(require.resolve('pele'));
const { Resvg } = require('@resvg/resvg-js');

const source = process.argv[2] ? readFileSync(process.argv[2], 'utf8') : readFileSync(0, 'utf8');
if (!source.trim()) {
  console.error('mermaid-diagram: no Mermaid text given (pass a file path or pipe it on stdin)');
  process.exit(2);
}

let result;
try {
  result = render(source, { maxWidth: PHONE_WIDTH, fontFamily: FONT, padding: 24, responsive: false });
} catch (e) {
  if (!(e instanceof PeleError)) throw e;
  const where = e.line ? ` at line ${e.line}, column ${e.column}` : '';
  console.error(`Mermaid ${e.code} error${where}: ${e.message.split('\n')[0]}${e.snippet ? '\n' + e.snippet : ''}`);
  process.exit(2);
}

const png = rasterise(result.svg, result.width, result.height);
mkdirSync(OUT_DIR, { recursive: true });
const stamp = new Date().toISOString().replace(/[-:]/g, '').replace('T', '-').slice(0, 15);
const file = join(OUT_DIR, `diagram-${stamp}-${randomBytes(3).toString('hex')}.png`);
writeFileSync(file, png.data);
console.log(`MEDIA:${file}`);
console.log(`size ${png.width}x${png.height} (${result.type})`);
if (Math.max(png.width, png.height) / Math.min(png.width, png.height) > 20) {
  console.error('warning: aspect ratio above 20:1, Telegram will send this as a file, not a photo. Split the diagram.');
}

function rasterise(svg, width, height) {
  // 1440 px wide reads sharply on a phone; small diagrams get at most 3x, and the
  // total is capped to stay inside Telegram's photo limit.
  let scale = Math.min(3, Math.max(1.5, 1440 / width));
  scale = Math.min(scale, MAX_SIDE_SUM / (width + height));
  const out = new Resvg(inlineCssVariables(svg), {
    fitTo: { mode: 'zoom', value: scale },
    background: '#ffffff',
    font: { loadSystemFonts: true, defaultFontFamily: 'Liberation Sans' },
  }).render();
  return { data: out.asPng(), width: out.width, height: out.height };
}

// Pele colours everything through CSS custom properties (fill="var(--_s)"). resvg
// cannot resolve them, and the raw SVG rasterises as black boxes with invisible text.
// Replace each var(--x, fallback) with the value the root <svg> assigns, or its fallback.
function inlineCssVariables(svg) {
  const rootStyle = (svg.match(/<svg\b[^>]*\sstyle="([^"]*)"/) || [, ''])[1];
  const vars = Object.fromEntries([...rootStyle.matchAll(/(--[\w-]+)\s*:\s*([^;]+)/g)].map(m => [m[1], m[2].trim()]));
  let out = svg;
  for (let pass = 0; pass < 4 && out.includes('var('); pass++) {
    out = out.replace(/var\((--[\w-]+)(?:\s*,\s*([^()]*))?\)/g, (m, name, fallback) => vars[name] ?? fallback ?? m);
  }
  // resvg ignores `rx` set in CSS; move it to the attribute so corners stay rounded.
  return out.replace(/(<rect\b[^>]*?)\sstyle="rx:\s*([\d.]+)(?:px)?;?/g, '$1 rx="$2" style="');
}
