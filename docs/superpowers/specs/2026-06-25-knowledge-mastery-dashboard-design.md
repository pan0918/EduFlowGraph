# Knowledge Mastery Dashboard Design

## Goal

Replace the current `Knowledge` workspace concept list with a high-fidelity "concept mastery dashboard" that closely follows the approved reference image. The first version is intentionally hardcoded and frontend-only, but the component structure and data shape should be ready for later runtime data integration.

## Scope

In scope:

- Redesign the `Knowledge` workspace into a dashboard-style page
- Use hardcoded subject and concept mastery data
- Implement working subject filters and search
- Preserve the existing `/knowledge` route
- Keep the rest of the application untouched
- Add targeted source-level coverage for the new dashboard structure

Out of scope:

- Backend or API changes
- Persisted search/filter state
- Live editing or update actions
- Real learning-plan generation
- Cross-page visual redesign

## Approved Direction

The user approved `方案 B`: a modular, high-fidelity recreation of the reference layout. The page should visually track the provided mockup closely, while the implementation stays maintainable and ready for future data wiring.

The user also approved using the reference image's content semantics directly for the initial pass, including:

- `概念掌握面板`
- subject-level mastery cards
- summary metrics
- right-rail weak concept list
- bottom learning suggestion callout

## Experience Goals

The page should feel noticeably more polished than the current `Knowledge` module:

- warm cream background with soft card surfaces
- large serif heading with stronger hierarchy
- elegant pill filters and search field
- clean two-column dashboard composition
- distinct color identity per subject card
- subtle decorative top-right background accents
- responsive layout that preserves hierarchy on smaller screens

This should read as a dashboard for a learner's concept mastery, not a raw memory-node browser.

## Information Architecture

### Header

- small eyebrow: `知识状态`
- large title: `概念掌握面板`
- supporting description
- right-aligned search input with placeholder `搜索概念、知识点或学科`

### Filter Row

Subject pills:

- `全部`
- `高中数学`
- `微积分`
- `线性代数`
- `语文`
- `英语`
- `大学物理`

### Summary Metrics

Four compact cards:

- subject count
- concept count
- mastered concepts and mastery rate
- weak concepts and attention rate

### Main Grid

Left:

- 6 subject mastery cards in a responsive grid
- each card shows subject icon, title, overview, mastery percentage, progress bar, concept tags, and a recommendation row

Right:

- a persistent `待强化概念` panel
- list rows include icon, concept name, subject lineage, and a status badge such as `薄弱` or `待提升`

### Footer Banner

- `学习建议` banner
- concise explanatory copy
- CTA button `生成学习计划`

## Data Model Strategy

The first pass uses hardcoded data colocated with the page or in a nearby frontend-only helper. The shape should be future-friendly rather than throwaway.

Suggested shape:

- `summary`: counts and mastery totals
- `subjects[]`: `id`, `name`, `icon`, `accent`, `overview`, `mastery`, `topics[]`, `recommendation`
- `weakConcepts[]`: `id`, `name`, `subject`, `topic`, `status`, `accent`
- `learningSuggestion`: `title`, `description`, `ctaLabel`

Search should match against:

- subject name
- subject overview
- topic labels
- weak concept names
- weak concept subject names

## Interaction Design

### Subject Filter

- Clicking a pill activates that subject
- `全部` resets filtering
- Filtering updates subject cards and weak concept rail together

### Search

- Client-side only
- Real-time filtering as the user types
- Works together with the active subject pill

### Empty State

If no subject or weak concept matches the current filter state, show a graceful empty result message inside the dashboard area instead of falling back to the old concept list.

## Implementation Notes

- Keep the `/knowledge` page entry unchanged
- Rebuild `KnowledgeWorkspace` into a composed dashboard rather than a `snapshot.concepts.map(...)` renderer
- Prefer local subcomponents first; only split files if `KnowledgeWorkspace.tsx` becomes too large to read comfortably
- Reuse existing Tailwind utilities and page-shell conventions where sensible
- Do not change backend contracts or `WorkspaceProvider`

## Testing

Add targeted source-level tests that assert the new dashboard structure exists and that the old raw concept-list rendering path is gone.

Verification should include:

- targeted Node test for the `KnowledgeWorkspace` source
- production build for the `web` app

## Risks and Mitigations

Risk: a close visual recreation could become brittle if overfit into one giant component.

Mitigation:

- keep data centralized
- keep repeated UI in subcomponents
- keep color and badge logic declarative

Risk: the dashboard may visually clash with the rest of the app.

Mitigation:

- stay inside the existing warm palette family
- push fidelity through spacing, hierarchy, and composition instead of importing alien styles
