# UofT Course Planning Agent

A student-built AI-assistant prototype for University of Toronto course
planning, initially focused on the **Cognitive Science Major — Science
Program, Computational Cognition Stream** (ASMAJ1446A). The agent uses
deterministic Python tools for requirement calculations and an LLM
back-end to explain results in natural language.

> **Proof of concept.** This project is not affiliated with or endorsed
> by the University of Toronto. It is not a replacement for Degree
> Explorer, the Academic Calendar, academic advising, or official
> program decisions. It is designed to surface uncertainty and
> manual-review cases — not to make final enrollment choices.

## Current capabilities

- **Prerequisite checking** — reports eligible, not_eligible, or
  manual_review_needed for complex prerequisite expressions
- **Exclusion checking** — detects credit-overlap conflicts between
  completed courses
- **Term availability** — checks whether a course is offered in Fall,
  Winter, or has UNKNOWN availability
- **Course details** — retrieves title, description, credits, breadth,
  and verification status from a structured catalog
- **Metadata verification** — surfaces needs_official_verification
  and UNKNOWN fields from the course data
- **Requirement-pool recommendations** — returns candidate courses
  from the Computational Cognition Stream pool with interest-based
  ranking and prerequisite pre-checks
- **Bounded multi-step ReAct agent** — the model can chain up to 2
  tool calls (e.g., check prerequisites, then check term availability)
  before producing a final answer
- **Explicit clarification action** — when the student provides
  insufficient information, the agent asks a targeted question instead
  of guessing
- **Deterministic program-progress audit engine** — evaluates every
  structured requirement, choice-group, and pool rule from program data
  without LLM-inferred counting
- **Stream-pool credit counting** — counts completed pool credits by
  level, designator, and 300-level-or-higher minimum
- **Special-rule evaluation** — CSC minimum (1.0), CSC maximum (2.0),
  designator concentration (1.5), 300-level minimum (1.0), all
  driven by structured program data
- **Separate progress and review statuses** — requirements can be
  "completed" in credits while still requiring manual review due to
  ambiguous expressions, unverified courses, or exclusion conflicts
- **Exclusion-conflict detection and course-allocation transparency** —
  reports conflicts without silently resolving them; never
  double-counts credits automatically

## Architecture

```
structured course / program data (JSON)
        │
        ▼
deterministic Python tools (src/tools.py, src/program_audit.py)
        │
        ▼
tool registry (src/tool_registry.py) — 7 registered tools
        │
        ▼
bounded multi-step agent (src/agent.py) — ReAct loop, max 2 steps
        │
        ▼
model back-end (src/model.py) — TencentTokenHubModel or MockModel
        │
        ▼
evaluation (eval/) — rule-based checks + LLM Judge
```

The LLM explains tool results in natural language, but every requirement
calculation, credit count, rule check, and exclusion detection is
performed by deterministic Python logic — not by the model.

## Knowledge base

- **95 courses** sourced from the UofT Arts & Science Academic Calendar
  (93 `calendar_verified`, 2 `needs_official_verification`)
- **Program requirements** for ASMAJ1446A: first-year, second-year,
  upper-year, approved pool, and capstone sections with structured
  choice-group options and explicit special-rule values
- Complex prerequisites stored with `manual_review_needed` handling
- CSC program restriction notes for 300-/400-level courses

## Reliability and evaluation

The current test suite passes locally with **554 automated tests** (`python3 -m pytest`).

**Core-5 evaluation batch** — a small curated set of 5 representative
cases run against the real TokenHub model:

| Case | Category | Result |
|------|----------|--------|
| Multi-step eligibility + term | prerequisite_reasoning | ✅ PASS |
| AI/ML pool recommendation | course_recommendation | ✅ PASS |
| Exclusion conflict | exclusion_conflicts | ✅ PASS |
| Unverified course handling | verification_uncertainty | ✅ PASS |
| Clarification action | insufficient_information | ✅ PASS |

> Core-5 is a small curated evaluation set (5 of 34 cases). It is not
> proof of production readiness. LLM Judge scores are non-deterministic
> and may vary between runs.

## Project structure

```
├── data/
│   ├── mock_courses.json              # 95-course catalog
│   └── mock_programs.json             # ASMAJ1446A program + structured rules
├── src/
│   ├── agent.py                       # Bounded multi-step ReAct loop
│   ├── model.py                       # TencentTokenHubModel + MockModel
│   ├── tools.py                       # Course lookup, prereqs, exclusions, term, recommendations
│   ├── tool_registry.py              # 7 registered tools
│   ├── program_audit.py              # Deterministic program-progress audit engine
│   └── mcp_server.py                 # MCP server stub
├── tests/
│   ├── test_agent.py                  # Agent loop, parsing, prompt content
│   ├── test_tools.py                  # Tool logic and data loading
│   ├── test_tool_registry.py         # Registry structure and dispatch
│   ├── test_model.py                  # Model interface and env-var handling
│   ├── test_program_audit.py         # Phase 1 + 2A + 2B1 audit tests
│   ├── test_evaluation.py            # Rule-based evaluator tests
│   └── test_llm_judge.py             # LLM Judge parsing and verdict tests
├── eval/
│   ├── evaluation_cases.json         # 34 evaluation scenarios across 8 categories
│   ├── judge_prompt.py               # LLM Judge system prompt
│   ├── run_evaluation.py             # Rule-based evaluator
│   ├── run_full_evaluation.py        # Full markdown-report evaluation runner
│   ├── run_llm_judge.py             # LLM Judge CLI (--case / --batch core5)
│   └── reports/                      # Generated evaluation reports
├── scripts/
│   ├── smoke_test_tokenhub.py        # Model connectivity test
│   ├── smoke_test_agent_tokenhub.py  # Single-step agent test
│   ├── smoke_test_multistep_tokenhub.py  # Multi-step agent test
│   └── smoke_test_program_audit_tokenhub.py  # Program-audit agent test
├── skills/
│   └── course_planning/
│       └── SKILL.md                   # Agent operating procedure
├── requirements.txt
└── .env.example                       # Environment variable template
```

## Setup

```bash
# Python 3.10+ recommended
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure TokenHub credentials (for live evaluation)
cp .env.example .env
# Edit .env with your TokenHub API key, base URL, and model name
```

**Never commit `.env`.** It is listed in `.gitignore`.
`.env.example` contains placeholders only.

## Running tests

```bash
python3 -m pytest
# 554 passed
```

All tests use MockModel — no API keys or network calls required.

## Running examples

**TokenHub smoke test** (requires `.env`):

```bash
python3 scripts/smoke_test_multistep_tokenhub.py
```

**Program-audit agent smoke test** (requires `.env`):

```bash
python3 scripts/smoke_test_program_audit_tokenhub.py
```

**Core-5 evaluation with LLM Judge** (requires `.env`):

```bash
python3 eval/run_llm_judge.py --batch core5
```

**Single-case rule-based evaluation** (no API keys needed):

```bash
python3 eval/run_full_evaluation.py --case multistep_csc384h1_winter
```

## Known limitations

- **Mock dataset** — 95 courses; not the full UofT calendar. Some
  courses, programs, and term data are absent.
- **No Degree Explorer integration** — this is a standalone prototype.
- **Grades, transfer credits, and waivers** are not supported in the
  audit engine.
- **Official double-counting decisions** are flagged as
  manual_review_needed rather than automatically resolved.
- **Term availability data** may be incomplete (73 courses have UNKNOWN
  term).
- **Ambiguous official expressions** (e.g., the first-year math
  pathway) are preserved with manual_review_needed rather than silently
  interpreted.
- **LLM Judge scores are non-deterministic** — they vary between runs
  and should not be treated as ground truth.
- **Not production-ready.** Official verification remains necessary for
  all enrollment decisions.

## Security

- API keys are loaded from environment variables only (never hard-coded)
- `.env` is ignored by Git
- `.env.example` contains placeholders only
- Smoke-test and evaluation scripts never print API keys or secrets

## License

This project is a student-built proof of concept. See individual files
for attribution.
