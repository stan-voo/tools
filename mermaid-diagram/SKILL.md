---
name: mermaid-diagram
description: >
  Diagram as an image in a chat reply: write Mermaid, render it to a phone-sized PNG on the
  host, send it with a MEDIA line. Use when the user asks for a diagram, a scheme, a flow or a
  map, in any language, and when the shape of the answer is the point: a flow, a sequence, a
  loop, a decision, how parts connect.
---

# Mermaid diagram → PNG → chat

Raw Mermaid arrives in Telegram as a code block, so a diagram goes out as a picture. The
renderer is Pele (Obsidian's Mermaid renderer) plus resvg, run with Node on the host, no browser.

## Steps

1. **Write the Mermaid to a file** with the file tool, e.g. `/tmp/diagram.mmd`. A long
   inline terminal command can be blocked by the command guard, so the source always goes
   through a file.
2. **Render it** with `scripts/render.mjs` from this skill's folder:
   `node ~/.hermes/skills/mermaid-diagram/scripts/render.mjs /tmp/diagram.mmd`
   That is the path for a default install. Under a category folder or a profile, use the
   `scripts/render.mjs` beside this SKILL.md.
   Done when it prints `MEDIA:/…/cache/images/diagram-….png`.
   - **Exit 2** prints the bad line and column. Fix that line and render again, twice at
     most. Still failing: send the same structure as a short bulleted outline and say in
     one line that the picture failed.
   - **Exit 3** means the renderer's packages are not installed yet. Send the outline, and
     give the user the one-line install command the script printed.
3. **Reply** with a one-line caption saying what the picture shows, then the `MEDIA:` line
   exactly as printed, on its own line. The gateway turns that line into the image. The
   Mermaid source stays out of the reply.

## Drawing for the phone

- **Small:** about 12 nodes at most. A bigger idea becomes two diagrams, each rendered and
  sent with its own `MEDIA:` line.
- **Labels:** up to five words, in the language of the conversation. Node IDs stay short
  ASCII (`A`, `B`, `capture`); the text goes in the label: `A[Voice note]`.
- **Direction:** write `flowchart TD`. A wide `LR` chart is turned top-to-bottom anyway.
- **Types that work:** `flowchart`, `sequenceDiagram`, `stateDiagram-v2`, `timeline`,
  `mindmap`, `erDiagram`, `gantt`, `pie`, `quadrantChart`, `journey`.
- **Colour** only when it carries meaning: `style A fill:#ffe08a` or a `classDef`. The
  default grey is the house look.

## Syntax that renders

These cover every failure in a sample of 721 real diagrams:

- A label with punctuation, brackets or a colon goes in double quotes once:
  `B["Builder agent(s)"]`, `C["Stage 1: gates"]`. One pair of quotes, never `""…""`.
- Inner quotes become single quotes: `D["the 'parked' ideas"]`.
- State names are bare identifiers. A long name gets an alias:
  `state "Accepted for work" as accepted`, then `[*] --> accepted`.
- Flowchart node IDs are bare words too. `"Slack uploads file" --> X` fails; write
  `slack["Slack uploads file"] --> X`.
