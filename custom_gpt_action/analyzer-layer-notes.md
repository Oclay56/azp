# AZP Analyzer Context Layers

These notes replace the loose text files as implementation guidance. They are not a promise that AZP can beat the book. They define how the analyzer should use context without hallucinating picks or pretending unsupported data is live.

## Core Rule

Stake availability comes first.

The analyzer may only add context to a prop that already exists in the live Stake-backed AZP response. It must not create players, lines, markets, or odds from these notes.

## Layer 1: Distribution And Volatility

Use this as small tags, score nudges, and risk flags.

- Hits:
  - `under 1.5` can receive a small support tag because MLB hits cluster heavily at zero and one.
  - `under 0.5` must be marked risky because there is no cushion.
  - `over 1.5` must be marked as multi-hit dependent.
- Total bases:
  - Mark as right-tail sensitive because doubles, triples, and home runs can distort averages.
  - Overs need extra-base support.
  - Unders can receive light support, but not a hard boost.
- Home runs:
  - Always mark as rare-event / high-variance.
- Runs and RBI:
  - Mark as game-script dependent.
  - Do not let these markets flood a slip without a strong reason.
- Pitcher strikeouts:
  - Mark as pitcher-management sensitive.
  - Overs need workload leash.
  - Unders can benefit from early hook or pitch-count risk, but that is not automatic.

## Layer 2: Umpire Impact

This layer is corrected but deferred unless AZP has a real umpire source.

Important correction:

- Wide-zone / K-friendly umpire:
  - Helps strikeout overs.
  - Hurts pitcher strikeout unders.
  - Can support hitter counting-stat unders.
- Tight-zone / hitter-friendly umpire:
  - Helps pitcher strikeout unders.
  - Hurts strikeout overs.
  - Can make hitter unders riskier.

If umpire data is unavailable, AZP should not penalize every prop. It should mark the layer as deferred.

## Layer 3: Game Script And Positioning

Use these as explanations and warnings, not absolute rules.

- Multiple same-game unders can point to a low-scoring script.
- Pitcher dominance plus opponent batter unders can be coherent, but correlation-sensitive.
- Batter overs plus opposing pitcher damage overs can be coherent, but correlation-sensitive.
- Contradictory legs should be warned, not hidden silently.

## Layer 4: GPT Behavior

The Custom GPT should:

- Use exact AZP selections, lines, and odds.
- Show `contextualEdge.tags` and `riskFlags` when present.
- Treat context tags as reasons/warnings, not proof.
- Return fewer picks when good picks do not exist.
- Never fill missing legs with invented players or stale examples.

## Current Implementation

Implemented now:

- Distribution tags for hits, total bases, and home runs.
- Game-script / volatility risk for runs and RBI.
- Pitcher-management sensitivity for pitcher markets.
- Corrected optional umpire handling when `umpireContext` is present.
- Deferred umpire note when no umpire source exists.

Not implemented yet:

- Live umpire source.
- Weather source.
- Lineup card confirmation.
- True probability model.
- Monte Carlo parlay simulation.

Those should be added only when we have reliable data sources and tests.
