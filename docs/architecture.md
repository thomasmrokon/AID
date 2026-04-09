# AID System Architecture

## Overview

The Augmented Industrial Designer (AID) is a multi-agent AI system organized around a **Blackboard Architecture**. Five specialized agents read from and write to a shared state object (the *Shared Context*), coordinated through the OpenClaw orchestration platform.

## Infrastructure
## The Blackboard Pattern

The **Shared Context** (`shared-context.json`) acts as the central blackboard. All agents read the current state before reasoning and write their results back after completing their task.

## The Formal Spatial Language

### Layer 1 — Vocabulary
- PRODUKTIONSZELLE, PUFFER, ANDOCKZONE, LAGER, TECHNIKRAUM

### Layer 2 — Grammar
- MUSS_GRENZEN_AN (hard), BENOETIGT_NAHE (soft), DARF_NICHT_GRENZEN_AN (hard)

### Layer 3 — Syntax
- FISCHGRAETE, U_FLUSS, HALLENRASTER

## Agent Pipeline

User-Requirements → Produktionsablauf → Layout → Tragwerk → TGA → Consensus Check

## Consensus Protocol

- violations == 0
- conflicts == 0
- syntaxScore >= 0.8

## Model Routing

| Task | Provider |
|------|----------|
| Requirements | anthropic/claude-sonnet-4-6 |
| Layout | anthropic/claude-sonnet-4-6 |
| Validation | openai or google |
