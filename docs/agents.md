# AID Agent Specifications

## Agent 1 — User-Requirements
Elicits and formalizes client requirements into structured planning constraints.
**Model**: anthropic/claude-sonnet-4-6

## Agent 2 — Produktionsablauf
Models the production sequence and derives spatial adjacency requirements.
**Model**: anthropic/claude-sonnet-4-6

## Agent 3 — Layout
Generates a concrete spatial arrangement satisfying all grammar rules.
**Model**: anthropic/claude-sonnet-4-6

## Agent 4 — Tragwerk
Validates structural feasibility — column grids, span widths, load-bearing.
**Model**: openai or google

## Agent 5 — TGA
Checks building services (HVAC, electrical, plumbing, fire safety) integration.
**Model**: openai or google

## Shared Context Schema

```json
{
  "version": "1.0",
  "sessionId": "",
  "requirements": {},
  "productionFlow": {},
  "layout": {},
  "tragwerk": {},
  "tga": {},
  "consensus": {
    "violations": 0,
    "conflicts": 0,
    "syntaxScore": 0.0,
    "status": "pending"
  }
}
```

## Conflict Resolution

1. Conflict detected during consensus check
2. Both agents receive each other's output as context
3. Layout agent re-invoked first
4. Tragwerk re-validates
5. After 3 iterations → escalate to user
