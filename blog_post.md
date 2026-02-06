# How We Used a 0.5B Parameter Model to Generate Structured Financial Queries — and Why Output Control Changes Everything

[![Foundry Local](https://img.shields.io/badge/Foundry_Local-Local_Inference-0078D4?style=flat&logo=microsoft&logoColor=white)](https://learn.microsoft.com/en-us/azure/ai-foundry/foundry-local/get-started)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)

*A developer's guide to making small local models reliable enough for domain-specific structured output — without GPUs that cost more than your car.*

---

## The Problem: Big Models, Big Costs, Big Latency

If you've worked in financial services  or any regulated industry you've likely seen the pattern: an institution needs to translate natural-language questions into structured, auditable queries over internal data. Think Morgan Stanley analysts asking *"Calculate Net Interest Margin by product for UK in Q1 2025"* and expecting back a precise, schema-valid execution plan that can be run against internal datasets.

The obvious approach? Throw GPT-4 or Claude at it. And that works — until you account for:

- **Data sovereignty**: Financial data can't leave the building (or often even the machine)
- **Latency**: Real-time analytics needs sub-second responses, not 3–5 second API round-trips
- **Cost**: At scale, cloud LLM calls for every analyst query add up fast
- **Auditability**: Regulators want to know *exactly* what model produced what output, running where

So we asked: **Can a 0.5B parameter model, running entirely on a developer laptop, produce the same structured output as a 70B+ cloud model?**

The answer is yes, with the right architecture. This post walks through exactly how.

---

## The Architecture: Don't Ask the Model to Be Smart — Ask It to Be Precise

The core insight is that small models aren't bad at structured output,  they're bad at *unguided* structured output. A 0.5B model asked to "generate a financial query plan" will hallucinate fields, invent operators, and produce malformed JSON. But the same model, given a JSON Schema in its system prompt, a pre-built skeleton to fill in, and a validation loop that catches errors, that model produces valid output on the first or second attempt the majority of the time.

This is the principle behind **output control** (sometimes called constrained decoding or guided generation). Instead of hoping the model outputs the right structure, we *constrain* it.

Here's the full pipeline:

```
User Prompt
    │
    ▼
┌─────────────────────────┐
│  FinancialOntologyAgent  │  Deterministic: classify domain, map terms → metrics
└─────────┬───────────────┘
          │
┌─────────▼───────────────┐
│  QueryPlannerAgent       │  Deterministic: build plan skeleton (filters, time range, group_by)
└─────────┬───────────────┘
          │
┌─────────▼───────────────┐
│  QueryPlanGeneratorAgent │  MODEL CALL: fill in the skeleton → full JSON QueryPlan
└─────────┬───────────────┘
          │
┌─────────▼───────────────┐
│  OutputControllerAgent   │  Validate against schema; repair loop (max 2 retries)
└─────────┬───────────────┘
          │
┌─────────▼───────────────┐
│  ExecutorAgent           │  Deterministic: run plan over local JSON data files
└─────────┬───────────────┘
          │
┌─────────▼───────────────┐
│  ExplainerAgent          │  MODEL CALL: human-readable summary + safety notes
└─────────────────────────┘
```

**Six agents. Only two call the model. Four are deterministic.** That's the key ratio.

![Landing Page — demo cards for Finance, Risk, Treasury, and AML domains](screenshots/01-landing-page.png)

---

## Technique 1: The Financial Ontology — Constrain Before You Generate

Before the model sees anything, a deterministic `FinancialOntologyAgent` classifies the user's prompt into a domain and maps natural-language terms to canonical metric identifiers.

```python
ONTOLOGY = {
    "NII": {
        "canonical": "NII",
        "label": "Net Interest Income",
        "formula": "interest_income - interest_expense",
        "dataset": "interest",
        "keywords": ["net interest income", "nii", "interest margin income"],
    },
    "ECL": {
        "canonical": "ECL",
        "label": "Expected Credit Loss",
        "formula": "PD × LGD × EAD",
        "dataset": "loans",
        "keywords": ["expected credit loss", "ecl", "credit loss", "ifrs 9", "stage migration"],
    },
    # ... 5 metrics across 4 domains
}
```

When a user asks *"Show loans that migrated from Stage 1 to Stage 2 and compute expected credit loss"*, the ontology agent maps this to `domain=Risk`, `metrics=["ECL"]`, `dataset=loans` all without a single model token generated.

**Why this matters for small models**: A 0.5B model doesn't need to figure out that "expected credit loss" means `ECL` or that it maps to the `loans` dataset. That information is already resolved. The model only needs to fill in the remaining structural details a dramatically simpler task.

This is the same pattern that firms like Morgan Stanley use: a well-defined financial glossary (we ship a 32-term one covering Finance, Risk, Treasury, and AML domains) that maps analyst vocabulary to canonical system terms, removing ambiguity before the model ever sees the prompt.

---

## Technique 2: The Plan Skeleton — Why "Half the Answer" Is the Right Prompt

The `QueryPlannerAgent` runs *before* the model and builds a partial plan skeleton using simple regex and keyword extraction:

```python
# Detect time range from "Q1 2025"
m = re.compile(r"Q([1-4])\s*(\d{4})").search(text)
# → {"start": "2025-01-01", "end": "2025-03-31"}

# Detect region from "UK"
region = _detect_region(text)  # → "UK"

# Detect grouping from "by product"
if "by product" in lower:
    group_by.append("product")
```

The skeleton passed to the model looks like this:

```json
{
  "domain": "Finance",
  "intent": "Calculate Net Interest Margin by product for UK in Q1 2025",
  "dataset": "interest",
  "metrics": ["NIM"],
  "filters": [{"field": "region", "op": "=", "value": "UK"}],
  "group_by": ["product"],
  "time_range": {"start": "2025-01-01", "end": "2025-03-31"}
}
```

The model's job is now **completion, not generation**. It takes this skeleton and produces a full, schema-valid QueryPlan, adding explanation requirements, validating field names, and ensuring the plan is structurally complete. That's a much easier task than generating the entire plan from scratch.

**The analogy**: It's like giving a junior analyst a filled-out template and asking them to review it, versus giving them a blank form and a vague instruction. The first task has a dramatically higher success rate.

---

## Technique 3: JSON Schema in the System Prompt — The Model's Guardrails

The `QueryPlanGeneratorAgent` injects the full JSON Schema directly into the model's system prompt:

```python
_SYSTEM_PROMPT = """You are a banking analytics query planner.
You MUST output ONLY a single valid JSON object conforming to the provided JSON Schema.
Do NOT output any text, markdown, or explanation — ONLY the JSON object.

JSON Schema:
{schema}

Guidelines:
- domain must be one of: Finance, Risk, Treasury, AML
- dataset must be one of: interest, loans, liquidity, transactions
- metrics must be from: NII, NIM, ECL, NSFR, STRUCTURING_FLAG
- filters use field/op/value where op is one of: =, !=, >, <, >=, <=, in, contains
- All date strings must be YYYY-MM-DD format
"""
```

Combined with **low temperature** (`0.1`) and **capped `max_tokens`** (`2048`), this reduces the model's output space dramatically. The model isn't "being creative" — it's filling in a constrained form.

**Key technical detail**: We use Draft 7 JSON Schema with `enum` constraints on critical fields like `domain`, `dataset`, `metrics`, and filter `op`. This means even if the model hallucinates a value, the validator will catch it immediately.

```json
{
  "metrics": {
    "type": "array",
    "items": {
      "type": "string",
      "enum": ["NII", "NIM", "ECL", "NSFR", "STRUCTURING_FLAG"]
    }
  }
}
```

---

## Technique 4: The Repair Loop — When the Model Gets It Wrong (and It Will)

Even with all the above, a 0.5B model will sometimes produce invalid JSON. Maybe it adds a trailing comma, truncates the output at `max_tokens`, or invents a field that doesn't exist in the schema. This is expected.

The `OutputControllerAgent` implements a **validate-and-repair loop**:

```
Output from Generator
        │
        ▼
   Parse JSON ─── fail ──→ Try repair truncated JSON
        │                        │
     success                  success/fail
        │                        │
        ▼                        ▼
  Validate vs Schema ─── fail ──→ Build repair prompt with errors
        │                              │
     success                     Model generates fixed JSON
        │                              │
        ▼                         (max 2 retries)
   Return valid plan                   │
                                       ▼
                              Still invalid? Return
                              schema-valid error object
```

The repair prompt is surgical, it shows the model its own broken JSON *and* the specific validation errors:

```python
repair_prompt = (
    f"Original JSON (invalid):\n{current_text}\n\n"
    f"Validation errors:\n" + "\n".join(current_errors) + "\n\n"
    f"Fix the JSON. Output ONLY the corrected JSON object."
)
```

And critically, the repair uses `temperature=0.0`, we want the model to be as deterministic as possible when fixing errors.

**The safety net**: If validation still fails after 2 retries, the system doesn't crash or return garbage. It returns a **schema-valid error object**:

```python
def build_error_plan(domain, dataset, error_type, message, repair_attempted):
    return {
        "domain": domain,
        "intent": "error",
        "dataset": dataset,
        "error": {
            "type": error_type,
            "message": message,
            "repair_attempted": repair_attempted,
        },
    }
```

This means downstream agents (executor, explainer) always receive valid input. The pipeline never breaks — it degrades gracefully.

---

## Technique 5: Truncated JSON Recovery — Handling the `max_tokens` Cliff

Small models with limited context windows often hit the `max_tokens` limit mid-JSON-object. You get output like:

```json
{"domain":"Finance","intent":"Calculate NIM","filters":[{"field":"region","op":"=","valu
```

Our `_try_repair_truncated_json` function handles this before the repair loop even kicks in:

```python
def _try_repair_truncated_json(text):
    s = text.rstrip()
    # Strip trailing incomplete string literal
    s = re.sub(r',?\s*"[^"]*$', '', s)
    # Strip trailing incomplete key-value pair
    s = re.sub(r',?\s*"[^"]*"\s*:\s*$', '', s)
    # Strip dangling comma
    s = s.rstrip().rstrip(',')
    # Close open braces and brackets
    open_braces = s.count('{') - s.count('}')
    open_brackets = s.count('[') - s.count(']')
    s += ']' * max(open_brackets, 0)
    s += '}' * max(open_braces, 0)
    return json.loads(s)  # May still fail — caller handles that
```

This simple heuristic recovers a surprising percentage of truncated plans without needing a model call at all.

---

## Technique 6: Deterministic Execution — The Model Doesn't Touch the Data

Once we have a valid QueryPlan, execution is **entirely deterministic**. The `ExecutorAgent` runs pure Python computation over local JSON files — no model involved:

```python
def _compute_nsfr(rows):
    results = []
    for r in rows:
        asf = r.get("available_stable_funding", 0)
        rsf = r.get("required_stable_funding", 0)
        nsfr = round((asf / rsf) * 100, 2) if rsf else 0
        results.append({
            "month": r.get("month"),
            "nsfr_pct": nsfr,
            "breach": nsfr < 100,
        })
    return results
```

This is deliberate. The model's job is narrowly scoped: **translate natural language → structured plan**. Everything else — filtering, aggregation, metric computation, breach detection — is code. Code that's testable, auditable, and guaranteed to produce correct results given valid input.

![Treasury NSFR compliance results with breach detection flagging months below 100%](screenshots/05-treasury-results.png)

---

## Technique 7: Multi-Agent Orchestration with Microsoft Agent Framework

The pipeline uses [Microsoft Agent Framework](https://github.com/microsoft/agents) patterns. Each agent inherits from `BaseAgent` and implements a single `async run()` method:

```python
class BaseAgent:
    name: str
    description: str

    async def run(self, message: AgentMessage) -> AgentMessage:
        raise NotImplementedError
```

The `CoordinatorAgent` wires them together in a linear pipeline, with an `AgentMessage` envelope carrying both `content` (text) and `data` (structured dict) between agents:

```python
class CoordinatorAgent(BaseAgent):
    async def run(self, message):
        ont_msg  = await self.ontology.run(message)       # 1. Classify
        plan_msg = await self.planner.run(planner_input)   # 2. Skeleton
        gen_msg  = await self.generator.run(gen_input)     # 3. Model → JSON
        ctrl_msg = await self.controller.run(ctrl_input)   # 4. Validate/repair
        exec_msg = await self.executor.run(exec_input)     # 5. Execute
        expl_msg = await self.explainer.run(explain_input) # 6. Explain
        # ... merge and return
```

The trace is captured at each step, giving full visibility into what each agent decided:

![Full agent trace showing all 6 pipeline steps](screenshots/03-agent-trace.png)

---

## The Results: What a 0.5B Model Actually Achieves

Running on **Qwen 2.5 0.5B** via [Microsoft Foundry Local](https://learn.microsoft.com/en-us/azure/ai-foundry/foundry-local/get-started) (CUDA GPU), here's what the pipeline produces for *"Calculate Net Interest Margin by product for UK in Q1 2025"*:

![Finance demo — NIM results by product with summary metrics and data table](screenshots/02-finance-results.png)

The model generates a valid QueryPlan on the first attempt. The deterministic executor computes NIM across three product groups (Mortgage, SME Loan, Credit Card), and the explainer produces a clear narrative with safety notes.

**Pipeline timing**: ~14–17 seconds end-to-end on a laptop GPU. That includes two model calls (generator + explainer). The deterministic agents (ontology, planner, executor) complete in milliseconds.

| Component | Time | Model Call? |
|-----------|------|-------------|
| Ontology Agent | <1ms | No |
| Planner Agent | <1ms | No |
| Generator Agent | ~5–8s | Yes |
| Output Controller | <1ms (if valid) | Only on repair |
| Executor Agent | <5ms | No |
| Explainer Agent | ~5–8s | Yes |
| **Total** | **~14–17s** | **2 calls** |

---

## When the Model Fails — and Why That's OK

The 0.5B model doesn't always get it right. Complex AML queries with multiple conditions sometimes exhaust the repair loop. When that happens, the pipeline returns a clean error:

> *"Failed to produce valid QueryPlan after 2 retries. Errors: JSON parse error: Unterminated string..."*

**This is an intentional design choice.** The system never returns invalid output. It either succeeds with a correct plan, or it fails with a schema-valid error object that the UI can display meaningfully. There's no silent corruption.

For production use, you'd tune this by:
1. **Upgrading the model** — Qwen 2.5 7B would dramatically improve first-pass accuracy
2. **Adding few-shot examples** — 2–3 examples of valid plans in the system prompt
3. **Using structured output APIs** — Some inference servers support grammar-constrained decoding
4. **Expanding the repair budget** — More retries for complex domains

---

## The Glossary: Your Secret Weapon

We ship a 32-term financial glossary covering four domains:

![Sidebar glossary with 32 financial terms across Finance, Risk, Treasury, and AML](screenshots/04-glossary-sidebar.png)

Each glossary entry includes the canonical term, synonyms, formula, regulatory context, and an example prompt:

```json
{
  "term": "ECL",
  "full_name": "Expected Credit Loss",
  "domain": "Risk",
  "definition": "Forward-looking estimate of credit losses...",
  "formula": "PD × LGD × EAD",
  "dataset": "loans",
  "synonyms": ["credit loss provision", "impairment charge", "IFRS9 ECL"],
  "regulatory_context": "IFRS 9 / CECL"
}
```

**Why this matters**: In a real deployment (like a financial query generation system), the glossary is your controlled vocabulary. It ensures that whether an analyst says "credit loss provision", "impairment charge", or "ECL", everyone gets the same metric. The ontology agent uses these synonyms for detection, and the model receives the canonical terms. Eliminating an entire class of ambiguity errors that even large models struggle with.

---

## How to Implement This Yourself

### Step 1: Define Your Schema

Start with the output format you need. Be specific use `enum` constraints wherever possible:

```json
{
  "domain": { "type": "string", "enum": ["Finance", "Risk", "Treasury", "AML"] },
  "metrics": { "items": { "enum": ["NII", "NIM", "ECL", "NSFR"] } }
}
```

The tighter your schema, the less room the model has to hallucinate.

### Step 2: Build Your Ontology

Map every term your users might use to a canonical identifier. Include synonyms:

```python
ONTOLOGY = {
    "NIM": {
        "keywords": ["net interest margin", "nim", "margin", "interest margin"],
        "dataset": "interest",
    }
}
```

### Step 3: Implement Deterministic Pre-Processing

Extract everything you can *before* calling the model: dates, regions, entities, filter conditions. Build a skeleton that the model just needs to validate and complete.

### Step 4: Constrain the Model

- Put the JSON Schema in the system prompt
- Use low temperature (0.1 or lower)
- Cap `max_tokens`
- Instruct it to output **only** JSON

### Step 5: Validate and Repair

Use `jsonschema` (or equivalent) to validate immediately. On failure, send a repair prompt with the specific errors. Cap retries at 2–3 to avoid infinite loops.

### Step 6: Fail Gracefully

Always have a schema-valid error object. Never return invalid output.

---

## Running the Demo

```bash
# Clone and set up
git clone <repo-url> bankquery-copilot-local
cd bankquery-copilot-local
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# Install Foundry Local
winget install Microsoft.FoundryLocal   # Windows
brew install foundrylocal               # macOS

# One-command start
.\start.ps1                             # PowerShell
./start.sh                              # Bash
```

Or run in mock mode (no Model required this is simulation):

```bash
set MOCK_MODE=1
streamlit run app.py
```

---

## Key Takeaways for Developers

1. **Small models are viable for structured output** — if you constrain them properly. A 0.5B model with schema injection + repair loop outperforms a 7B model generating free-form JSON.

2. **Do the hard work deterministically.** Ontology mapping, date parsing, filter extraction — these are all tasks where code is faster, cheaper, and more reliable than any model.

3. **The model's job should be narrow.** In our pipeline, the model does exactly two things: fill in a plan skeleton and write an explanation. Everything else is code.

4. **Validation isn't optional — it's the architecture.** The repair loop isn't a nice-to-have; it's what makes the system production-grade. Without it, you're hoping the model gets it right. With it, you're guaranteeing a valid output every time.

5. **Local inference changes the economics.** Running Qwen 2.5 0.5B on a laptop GPU costs $0 per query. At financial institution scale (thousands of analysts, millions of queries), that's the difference between a viable product and an unsustainable cost centre.

6. **Graceful degradation > silent failure.** A schema-valid error object that says "I couldn't do this" is infinitely more useful than malformed JSON that breaks downstream systems.

---

## What's Next

- **Grammar-constrained decoding**: Foundry Local and other engines are adding support for GBNF/JSON Schema-constrained sampling this would eliminate the repair loop entirely
- **Larger local models**: As hardware improves, 7B and 14B models become viable on laptops, dramatically improving first-pass accuracy
- **Fine-tuning**: Domain-specific fine-tuning on financial query plans would further reduce errors but the output control architecture means you don't *need* to fine-tune to get started
- **Agentic evaluation**: Using tools like AI Toolkit to measure first-pass validity rates across prompt categories

---

## References

- [Microsoft Foundry Local — On-Device AI Inference](https://learn.microsoft.com/en-us/azure/ai-foundry/foundry-local/get-started)
- [Microsoft Agent Framework](https://github.com/microsoft/agents)
- [JSON Schema Specification (Draft 7)](https://json-schema.org/draft-07)
- [Guidance — Microsoft's Structured Output Library](https://github.com/guidance-ai/guidance)
- [Qwen 2.5 Model Family](https://qwenlm.github.io/blog/qwen2.5/)

---

*This project is open-source under the MIT License. All financial data is synthetic. AML outputs are heuristic demonstrations only — not suitable for real regulatory filings.*
