# Memory Graph UI Design

## Goal

Replace the current column-based "graph view" in the memory workspace with a visually dominant radial memory graph that feels like a graph first and a dashboard second.

The redesigned page should:

- make the graph the primary visual artifact on the page
- avoid exposing internal identifiers such as `node_id`, `edge_id`, or segment ids in the default view
- reveal node details only on hover
- preserve the existing memory data model (`concept`, `episode`, `skill`, `event`, `edge`) without inventing fake graph entities
- keep supporting lists and counts available, but visually secondary

## Current Problems

The current implementation in `/Users/frud_/Desktop/AITutor/web/components/workspace/MemoryWorkspace.tsx` renders the "graph" as five vertical columns of cards. That structure has three problems:

1. It does not communicate relationships spatially, so it reads like a grouped list rather than a graph.
2. It surfaces too much internal metadata inline, including fallback ids and technical event names.
3. It gives equal visual weight to primary memory nodes and secondary diagnostic records, which makes the page feel noisy and uncurated.

## Design Direction

Use a concentric radial graph as the hero visualization for the memory page.

The visual language should feel calm, editorial, and precise rather than playful or highly technical:

- warm neutral background that stays consistent with the existing product palette
- low-contrast rings and connector lines
- restrained accent colors by node family
- minimal always-on text
- hover-driven detail disclosure

This design is inspired by the user's reference image, but it is adapted to the current project data model rather than copied literally.

## Information Architecture

The memory page will be reorganized into three vertical zones:

### 1. Header band

A compact top band containing:

- page title: `记忆图谱`
- one-line subtitle explaining the layer model
- a `刷新` action button

This header should be visually light and should not consume hero space.

### 2. Primary graph stage

The dominant section on the page. It should occupy most of the first viewport height.

It contains:

- the radial graph canvas
- an in-canvas legend for node families
- a small bottom-left summary chip area for counts
- a hover tooltip panel that appears only while a node is active

This area replaces the current five-column "图谱视图" block completely.

### 3. Secondary diagnostics zone

All list-style supporting information becomes secondary and moves below the graph.

This area includes:

- compact metric cards
- retrieval health
- recent DataFlow events
- episode-concept edge details
- episode-skill edge details
- extraction counters

These sections remain available for debugging, but are visually deemphasized through smaller spacing, lighter headings, and optional collapsible containers where appropriate.

## Graph Layer Model

The radial graph uses three semantic layers mapped to the current project data model.

### L3 Center: Episodes

The innermost ring is the semantic core of the tutoring memory.

Rules:

- each `EpisodeNode` is rendered on the inner ring
- default label uses `episode.summary.title`
- no internal ids are shown
- recent or more strongly connected episodes receive slightly larger nodes

Rationale:

Episodes are the best current synthesis unit in the project, so they should anchor the whole graph.

### L2 Middle Ring: Concepts and Skills

The middle ring holds structured abstractions around episodes.

Rules:

- `ConceptNode` and `SkillNode` both live on the middle ring
- they are split into separate angular sectors rather than mixed randomly
- concept nodes are lighter and slightly smaller
- skill nodes are a bit more solid and visually anchored

Sector split:

- left-to-upper arc: concepts
- right-to-lower arc: skills

Rationale:

Concepts and skills are both structured memory, but users should be able to distinguish "what the student is learning" from "how the tutor teaches" at a glance.

### L1 Outer Ring: Events

The outer ring contains process traces.

Rules:

- extraction and validation events are rendered as small peripheral nodes
- failed events are included, but treated as subtle warnings rather than dominant failures
- event nodes default to no visible long label unless there is enough space

Included event families:

- `episode_extraction_completed`
- `concept_extraction_completed`
- `skill_evidence_recorded`
- `skill_distillation_completed`
- `skill_validation_recorded`
- `episode_extraction_failed`

Rationale:

Events are evidence and diagnostics, not the main memory object. They belong on the periphery.

## Relationship Rendering

The graph should communicate structure without turning into a hairball.

### Default state

- all edges render with very low contrast
- only structurally meaningful edges are included
- edge density is capped to avoid visual collapse

Visible edge families:

- `episode_concept`
- `episode_skill`
- event-to-episode association inferred from `segment_id` or provenance where possible

### Hover state

When the pointer enters a node:

- direct neighbors brighten
- unrelated nodes fade slightly
- directly connected edges become clearer and thicker
- the node tooltip appears

### No locked inspector in v1

The user specifically asked for information to disappear when the mouse leaves. Therefore:

- hover shows details
- mouse leave hides details
- click-to-lock is not included in v1

## Labeling Rules

The page should suppress technical noise aggressively.

### Always visible text

Only human-meaningful labels are shown by default:

- concept: `name`
- episode: `summary.title`
- skill: `name`
- event: short display label derived from event type

### Never shown inline by default

- `node_id`
- `edge_id`
- `segment_id`
- `episode_id`
- raw timestamps longer than needed
- retrieval metadata
- embedding metadata

### Density control

If the graph has too many nodes:

- only the most important labels stay visible
- the rest remain represented as dots until hovered

Importance heuristics:

- episodes with more linked nodes
- concepts referenced by more episode edges
- active skills over candidate skills

## Tooltip Content

Tooltip design must be compact, readable, and type-specific.

### Concept tooltip

- name
- aliases, if any
- description, if any
- count of linked episodes

### Episode tooltip

- title
- short topic summary
- detected learner problem
- learning outcome result, if any

### Skill tooltip

- name
- status
- difficulty pattern
- trigger
- first one or two procedure steps

### Event tooltip

- humanized event label
- timestamp
- short content or summary

Tooltip constraints:

- no internal ids
- maximum one short paragraph plus two or three metadata lines
- disappear immediately on mouse leave

## Visual System

### Color mapping

- episodes: warm amber
- concepts: soft green
- skills: muted violet
- successful process events: cool blue
- failed events: restrained rose

### Surface treatment

- graph stage sits inside a large rounded card-like container
- background rings use translucent strokes rather than filled wedges
- connectors are subtle, almost diagrammatic

### Motion

Only small purposeful motion is allowed:

- soft opacity transition on hover
- slight node emphasis scaling on hover
- tooltip fade

No springy or playful motion should be introduced.

## Layout and Responsiveness

### Desktop

- graph occupies the top hero region
- supporting sections sit below in one or two columns depending on width

### Tablet

- graph remains primary but reduces label density
- lower sections collapse into fewer columns

### Mobile

For the first implementation, the radial graph should degrade gracefully rather than try to fully preserve desktop complexity.

Rules:

- graph container remains visible
- label density is heavily reduced
- tooltip layout remains readable
- lower diagnostics stack vertically

The mobile goal is "usable and not broken", not full parity with desktop richness.

## Component Architecture

The redesign should keep logic isolated inside focused components.

### New components

Create a small graph component set under `web/components/workspace/memory-graph/`:

- `MemoryGraphStage.tsx`
  - overall graph stage container
  - legend
  - count summary
  - hover state ownership
- `MemoryGraphCanvas.tsx`
  - radial positioning and SVG rendering
- `MemoryGraphTooltip.tsx`
  - type-aware hover card
- `memoryGraphLayout.ts`
  - pure layout helpers for radial coordinates and node grouping
- `memoryGraphModels.ts`
  - normalized graph display types derived from `DashboardSnapshot`

### Existing component changes

`MemoryWorkspace.tsx` will:

- stop rendering the current `GraphColumn` grid
- use the new graph stage as the primary section
- move secondary diagnostics below the graph
- simplify the page intro copy

## Data Mapping Rules

The UI must derive display data from the existing `DashboardSnapshot` without requiring backend changes.

### Episode display nodes

Derived from `snapshot.episodes`.

### Concept display nodes

Derived from `snapshot.concepts`.

### Skill display nodes

Derived from `snapshot.skills`.

### Event display nodes

Derived from `snapshot.events`, but filtered to graph-relevant event types only.

### Display edges

Derived from:

- `snapshot.edges` for `episode_concept` and `episode_skill`
- inferred event associations using:
  - `event.segment_id`
  - `episode.provenance.segment_id`

If an event cannot be confidently associated to an episode, it may remain an unlinked outer-ring node or be omitted from the graph while still appearing in the diagnostics list.

## Error and Empty-State Behavior

### Empty memory

If there are no concepts, episodes, skills, or events:

- show a clean empty graph stage
- show a short sentence explaining that real memory will appear after actual tutoring dialogue
- do not inject demo nodes or fake examples

### Sparse memory

If only one or two node families exist:

- still render the graph
- keep unpopulated rings faintly visible
- avoid placeholder cards inside the graph stage

## Testing Strategy

### Unit-level logic tests

Add tests for pure layout/data helpers:

- grouping nodes by family
- mapping episodes, concepts, skills, and events into display nodes
- preserving human-readable labels while excluding internal ids
- event-to-episode association derivation

### Component behavior tests

Prefer focused React tests if the project already has suitable frontend test infrastructure. If that infrastructure is absent, keep the interaction logic simple enough to verify through build checks and pure helper tests first.

Critical behaviors to verify:

- no inline ids are rendered in the main graph labels
- hover state can produce the correct tooltip payload
- empty state renders without fake content

### Manual verification

Because visual quality is a core requirement, manual verification is required after implementation:

- inspect desktop layout
- inspect sparse-memory state
- inspect hover card behavior
- confirm lower diagnostics no longer dominate the page

## Out of Scope

The following are explicitly out of scope for this pass:

- click-to-lock inspector
- pan and zoom controls
- external graph library adoption
- backend API schema changes
- editing nodes from the graph
- search inside the graph

## Implementation Notes

The current frontend dependencies do not include a graph visualization package. For this pass, the graph should be built with native React + SVG so the design remains controlled and the dependency surface stays small.

This also reduces the risk of introducing a generic force-directed graph that looks technically functional but visually off-spec.
