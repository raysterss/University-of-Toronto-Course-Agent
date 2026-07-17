# Evaluation Layer

This directory contains manual evaluation cases for the UofT Cognitive Science
Course Planning Agent (ASMAJ1446A — Computational Cognition Stream).

## Purpose

The evaluation layer checks whether the agent exhibits correct **behaviors**,
not exact answer matching. A correct agent should:

- call appropriate tools for each scenario
- warn about uncertainty (UNKNOWN data, `needs_official_verification`,
  `manual_review_needed`)
- avoid hallucinating prerequisites or program rules
- respect program constraints (CSC credit caps, exclusions, breadth)
- ask clarifying questions when the student provides insufficient information

## Files

| File | Description |
|------|-------------|
| `evaluation_cases.json` | Structured evaluation scenarios with expected behaviors and failure conditions |
| `README.md` | This file — evaluation design and usage instructions |

## Case Structure

Each evaluation case in `evaluation_cases.json` contains:

| Field | Description |
|-------|-------------|
| `case_id` | Unique identifier (e.g., `recommend_ai_ml`) |
| `category` | One of 8 evaluation categories (see below) |
| `title` | Human-readable summary |
| `description` | Full scenario description and context |
| `student_profile` | Year, program, and target term |
| `completed_courses` | List of course codes the student has completed |
| `user_query` | The exact natural-language query to send to the agent |
| `expected_tools` | Tools the agent should call (empty if no tool call expected). For multi-step cases, all listed tools must be called for a PASS. |
| `expected_tool_sequence` | *(optional)* Ordered list of tool names. When present, the evaluator verifies the actual sequence matches the expected order. |
| `expected_behaviors` | Observable behaviors the agent should exhibit |
| `failure_conditions` | Things the agent must NOT do (hallucination, omission, etc.) |

## Case Inventory (34 cases)

### course_recommendation (5 cases)

| # | case_id | Scenario |
|---|---------|----------|
| 1 | `recommend_ai_ml` | AI/ML pool recommendation with interest filtering |
| 2 | `recommend_neuroscience` | Neuroscience-focused pool recommendation |
| 3 | `recommend_300_level` | 300+ level pool courses for upper-year student |
| 4 | `recommend_no_match` | Interest filtering returns no matches — still shows pool |
| 5 | `recommend_completed_many` | Well-prepared student — many courses should be eligible |

### prerequisite_reasoning (8 cases)

| # | case_id | Scenario |
|---|---------|----------|
| 6 | `prereq_simple_eligible` | Simple prerequisite — student is clearly eligible |
| 7 | `prereq_csc311_complex` | CSC311H1 — eligible with complex recommended prep |
| 8 | `prereq_missing_csc148` | Missing CSC148H1 — clearly ineligible |
| 9 | `prereq_complex_or_condition` | STA238H1 — OR condition in prerequisite |
| 10 | `prereq_grade_threshold` | CSC111H1 — 70% grade threshold required |
| 11 | `prereq_multi_component` | COG415H1 — multi-component prerequisites |
| 12 | `prereq_csc_cap` | CSC 300/400-level credit cap awareness |
| 13 | `multistep_csc384h1_winter` | 🆕 Multi-step: eligibility + Winter availability for CSC384H1 |

### exclusion_conflicts (3 cases)

| # | case_id | Scenario |
|---|---------|----------|
| 13 | `exclusion_csc108_csc148` | CSC108H1 retake — excludes CSC148H1 |
| 14 | `exclusion_sta237_sta247` | STA237H1 and STA247H1 are mutually exclusive |
| 15 | `exclusion_cog402_cog403` | Capstone mutual exclusion |

### term_availability (4 cases)

| # | case_id | Scenario |
|---|---------|----------|
| 16 | `term_fall_offered` | CSC165H1 offered in Fall — simple confirmation |
| 17 | `term_unknown_cog260` | COG260H1 has UNKNOWN term — must flag uncertainty |
| 18 | `term_not_offered` | Course may not be offered in requested term |
| 19 | `term_many_unknown` | Many pool courses have UNKNOWN terms — guidance needed |

### breadth_requirement (3 cases)

| # | case_id | Scenario |
|---|---------|----------|
| 20 | `breadth_unknown_lin232` | LIN232H1 has UNKNOWN breadth |
| 21 | `breadth_cog498_independent_study` | Independent study — UNKNOWN breadth explained |
| 22 | `breadth_multiple_courses` | Checking breadth coverage across courses |

### verification_uncertainty (4 cases)

| # | case_id | Scenario |
|---|---------|----------|
| 23 | `verify_mat137_unverified` | MAT137Y1 — needs_official_verification |
| 24 | `verify_mat157_unverified` | MAT157Y1 — needs_official_verification + exclusion |
| 25 | `verify_calendar_verified` | Calendar-verified course — present as reliable |
| 26 | `verify_csc_program_restriction` | CSC303H1 — program restriction in verification_note |

### program_requirements (4 cases)

| # | case_id | Scenario |
|---|---------|----------|
| 27 | `program_required_courses` | What courses are required for my program? |
| 28 | `program_math_pathway` | Choosing among math pathway options |
| 29 | `program_statistics_choice` | Statistics choice group planning |
| 30 | `program_pool_rules` | Understanding pool credit rules and restrictions |

### insufficient_information (3 cases)

| # | case_id | Scenario |
|---|---------|----------|
| 31 | `insufficient_no_info` | Vague query — should ask clarifying questions |
| 32 | `insufficient_no_completed` | Eligibility check without stating completed courses |
| 33 | `insufficient_no_term` | Recommendation without specifying target term |

## How to Evaluate

### CLI Evaluation Runner

```bash
# Run all 34 cases with MockModel:
python3 eval/run_full_evaluation.py

# Run a single case with MockModel:
python3 eval/run_full_evaluation.py --case multistep_csc384h1_winter

# Run a single case with the real TokenHub model:
python3 eval/run_full_evaluation.py --case multistep_csc384h1_winter --model tokenhub

# Run all cases in a category:
python3 eval/run_full_evaluation.py --category prerequisite_reasoning

# Write report to a custom path:
python3 eval/run_full_evaluation.py --output eval/reports/my_report.md
```

### Multi-Step Evaluation

Cases using `expected_tool_sequence` verify that the agent calls tools in the
correct order. The evaluator:

1. Checks that **all** tools in `expected_tools` were called (coverage).
2. Checks that the actual tool sequence **starts with** the expected sequence
   (ordering). Partial matches at the start are accepted — extra tools after
   the expected sequence do not cause a failure.
3. Combines observations from **all** steps when checking for uncertainty,
   verification warnings, CSC cap mentions, and course codes.
4. Evaluates `expected_behaviors` against the combined output of all steps,
   not just the final answer.

For example, `multistep_csc384h1_winter` expects:
- `check_prerequisites` → `check_term_availability` in that order
- The final answer must distinguish "course is available" from "student is eligible"

### Manual Evaluation

1. Run the agent smoke test with the TokenHub model:
   ```bash
   python3 scripts/smoke_test_agent_tokenhub.py
   ```

2. For each case, construct the `user_query` and `completed_courses` and observe:
   - Which tool was called? (`tool_called` in the output)
   - Does the thought and final answer exhibit the expected behaviors?
   - Are any failure conditions triggered?

3. Record pass/fail for each case.

### Evaluation Criteria

A case **passes** when:
- All `expected_behaviors` are observed (or reasonable equivalents)
- No `failure_conditions` are triggered

A case **fails** when:
- A required tool is not called
- A failure condition is triggered
- The agent hallucinates data not present in the catalog

### Known Limitations

- The evaluation cannot be fully automated because it requires judging
  natural-language outputs.
- Some behaviors may be expressed differently by the model and still be
  correct — use judgment.
- The evaluation does not check for exact answer wording, only for the
  presence of required information and the absence of misinformation.

## Core-5 Batch Evaluation

The `core5` batch is a curated set of 5 representative cases for manual
end-to-end evaluation with the real TokenHub model. It exercises all
major agent capabilities and is designed to catch regressions before
a full 34-case run.

### Selected Cases

| # | case_id | Category | Tools | What it tests |
|---|---------|----------|-------|---------------|
| 1 | `multistep_csc384h1_winter` | prerequisite_reasoning | check_prerequisites, check_term_availability | Multi-step eligibility + term |
| 2 | `recommend_ai_ml` | course_recommendation | recommend_courses_for_requirement | Interest-filtered pool recommendation |
| 3 | `exclusion_csc108_csc148` | exclusion_conflicts | check_exclusions | Exclusion conflict detection |
| 4 | `verify_mat137_unverified` | verification_uncertainty | get_course_metadata_status | `needs_official_verification` handling |
| 5 | `insufficient_no_completed` | insufficient_information | (clarify) | Clarification action when info missing |

### How to Run

```bash
# Run the core-5 batch:
python3 eval/run_llm_judge.py --batch core5

# With custom output:
python3 eval/run_llm_judge.py --batch core5 --output eval/reports/batch_core5.md
```

### What it evaluates

The batch runs each case through the full pipeline:
1. Agent execution (TokenHub model)
2. Rule-based evaluation (deterministic tool + behavior checks)
3. LLM Judge (semantic quality scoring)
4. Deterministic judge verdict calculation

A combined markdown report includes a summary table with per-case rule verdict, judge verdict, overall score, and hallucination risk, plus full individual judge reports.

### Warning

⚠️ **This is a manual evaluation tool, not pytest or CI.**

- Each case makes 2–4 TokenHub API calls (agent + judge). The core-5 batch makes approximately 15–20 API calls total.
- LLM judge scores are non-deterministic and may vary between runs.
- Never commit API keys or `.env` files.
- Use `--case` for single-case debugging before running the full batch.

## Design Principles

1. **Realistic scenarios**: Each case represents a plausible student
   interaction with the UofT Cognitive Science program.

2. **Behavior over output**: We evaluate what the agent does and warns
   about, not the exact phrasing of its answer.

3. **Boundary testing**: Cases cover edge conditions (UNKNOWN data,
   unverified courses, missing information) as well as happy-path
   scenarios.

4. **Program accuracy**: Cases encode known program rules (CSC credit cap,
   exclusions, verification statuses) drawn from the SKILL.md and course
   catalog data.

5. **Extensible**: New cases can be added by appending to the `cases`
   array in `evaluation_cases.json`. Follow the existing field structure.
