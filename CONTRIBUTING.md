# Contributing to bankquery-copilot-local

Thank you for your interest in contributing! This document provides guidelines to help you get started.

## Code of Conduct

This project follows the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/). By participating, you agree to uphold this code. Report unacceptable behaviour to the repository maintainers.

## How to Contribute

### Reporting Issues

- Use [GitHub Issues](../../issues) to report bugs or request features.
- Check existing issues before creating a new one.
- Include steps to reproduce, expected vs actual behaviour, and your environment details.

### Submitting Changes

1. **Fork** the repository.
2. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes** following the guidelines below.
4. **Run tests** to ensure nothing is broken:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate        # Windows
   source .venv/bin/activate     # macOS/Linux
   pip install -r requirements.txt
   set MOCK_MODE=1               # Windows
   export MOCK_MODE=1            # macOS/Linux
   pytest tests/ -v
   ```
5. **Commit** with a clear message:
   ```bash
   git commit -m "feat: add treasury LCR metric computation"
   ```
6. **Push** and open a **Pull Request** against `main`.

## Development Setup

```bash
git clone <your-fork-url>
cd bankquery-copilot-local
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Run the app in mock mode (no Foundry Local needed):
```bash
set MOCK_MODE=1
streamlit run app.py
```

## Project Structure

| Directory | Purpose |
|-----------|---------|
| `agents/` | Multi-agent pipeline (one file per agent) |
| `core/` | Shared utilities (Foundry client, executor, schema validation) |
| `data/` | Local JSON demo datasets + glossary |
| `schemas/` | JSON Schema for QueryPlan validation |
| `tests/` | pytest test suite |
| `demo/` | Curated demo prompts |

## Coding Guidelines

### General
- **Python 3.10+** — use type hints and `from __future__ import annotations`.
- Keep files short and focused — each agent is a single file.
- Use inline comments for non-obvious logic; avoid redundant docstrings.

### Agents
- Every agent inherits from `BaseAgent` and implements `async def run(self, message: AgentMessage) -> AgentMessage`.
- Deterministic agents (OntologyAgent, PlannerAgent, ExecutorAgent) must **never** call the model.
- Model-calling agents (GeneratorAgent, ExplainerAgent) must handle fallback gracefully.

### Schema & Validation
- All QueryPlan output **must** conform to `schemas/query_plan.schema.json`.
- If adding new metrics, update the schema's `metrics` enum, the executor, and the ontology.
- Error/refusal objects must also be schema-valid (use `build_error_plan()`).

### Data
- Demo data lives in `data/*.json` — keep it synthetic and small.
- Never include real customer, financial, or transaction data.
- When adding new datasets, follow the existing flat-JSON-array pattern.

### Glossary
- Financial terms go in `data/glossary.json`.
- Each entry must include: `term`, `full_name`, `domain`, `definition`, `formula`, `dataset`, `synonyms`, `example_prompt`, `unit`, `regulatory_context`.
- Use terminology consistent with Morgan Stanley, JPMorgan, HSBC conventions.

### Tests
- Tests use `pytest` and always run in mock mode (`MOCK_MODE=1` set in `conftest.py`).
- Add tests for any new metric, agent, or validation path.
- Test categories:
  - `test_schema.py` — schema conformance
  - `test_executor.py` — execution correctness
  - `test_repair.py` — repair loop + end-to-end pipeline

## Adding a New Metric

1. **Glossary:** Add the term to `data/glossary.json`.
2. **Ontology:** Add to `ONTOLOGY` dict in `agents/ontology_agent.py` with keywords.
3. **Schema:** Add to the `metrics` enum in `schemas/query_plan.schema.json`.
4. **Executor:** Add computation function in `core/executor.py` and wire it into `execute_query_plan()`.
5. **Data:** Ensure `data/*.json` has sufficient rows to demonstrate the metric.
6. **Tests:** Add test cases in `tests/test_executor.py`.
7. **Demo:** Optionally add a demo prompt to `demo/demo_prompts.jsonl`.

## Adding a New Agent

1. Create `agents/your_agent.py` inheriting from `BaseAgent`.
2. Wire it into the pipeline in `agents/coordinator_agent.py`.
3. Add tests covering the agent's behaviour.

## Commit Message Convention

Use [Conventional Commits](https://www.conventionalcommits.org/):

| Prefix | Usage |
|--------|-------|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `docs:` | Documentation only |
| `test:` | Adding or updating tests |
| `refactor:` | Code restructuring (no behaviour change) |
| `chore:` | Maintenance (deps, CI, config) |

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
