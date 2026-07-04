# ADR-001: Multi-Agent Architecture for Angela

> Date: 2026-07-02
> Status: Accepted
> Source: https://habr.com/ru/companies/alpinadigital/articles/1054436/

## Context

Angela was a monolithic agent handling:
- Role detection
- Knowledge base queries
- LLM generation
- Sales logic
- FAQ caching

As usage grew, problems emerged:
- Unpredictable behavior (autonomous agent)
- High API costs (~$600/month)
- Difficult to debug
- Poor test coverage

## Decision

We will split Angela into 3 specialized agents:

1. **Router** (Workflow - 70%)
   - Deterministic role classification
   - Topic detection
   - Complexity scoring

2. **KnowledgeBase** (Workflow - 70%)
   - FAQ lookup
   - Product catalog search
   - Vector memory
   - Client memory graph

3. **Generator** (Autonomous - 30%)
   - LLM with tier routing
   - Prompt caching
   - Response generation

## Consequences

### Positive
- 90% cost reduction (from ~$600 to ~$60/month)
- Predictable behavior (70% deterministic)
- Easier debugging (isolated components)
- Better test coverage (per-component)

### Negative
- Initial development time (~1 week)
- Need to maintain 3 components
- Migration complexity

### Risks
- Router misclassification → wrong agent
- KnowledgeBase stale data
- Generator hallucination

## Alternatives Considered

1. **Keep monolith** — rejected (cost, predictability)
2. **Full autonomous agent** — rejected (unpredictable, expensive)
3. **2 agents (Router + Generator)** — rejected (KB too complex for Generator)

## References

- Article: https://habr.com/ru/companies/alpinadigital/articles/1054436/
- Anthropic: https://www.anthropic.com/engineering/building-effective-agents
- DORA Report 2024: https://dora.dev/research/2024/dora-report/
