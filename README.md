# UofT Course Planning Agent

An AI agent engineering project exploring how a course-planning agent can help University of Toronto students in the **Cognitive Science Major — Science Program, Computational Cognition Stream** (ASMAJ1446A).

## What this project does

Course planning at UofT is complex. Students must satisfy program requirements, choice groups, approved course pools, prerequisite chains, exclusions, Breadth Requirements, and term availability — all at once. This project builds an agent that helps students reason through these constraints using structured data and deterministic tools.

The agent does not make decisions for students. It provides structured information, surfaces uncertainty, and reminds students to verify everything with official sources.

## Knowledge base

- **95 courses** sourced from the UofT Arts & Science Academic Calendar, with 93 `calendar_verified`
- **Program requirements** for ASMAJ1446A, structured into first-year, second-year, upper-year, approved pool, and capstone sections with preserved choice group expressions
- Complex prerequisites stored in `prerequisite_note` fields with `manual_review_needed` handling
- CSC program restriction notes for 300-/400-level courses (1.5-credit cap for non-CS-major students)

## Architecture

| Component | Description |
|---|---|
| **ReAct-style reasoning** | Step-by-step reason → act → observe → answer loop for multi-step planning tasks |
| **Structured knowledge base** | JSON course catalog and program data with verification status and metadata |
| **Deterministic tools** | Python functions for course lookup, prerequisite checking, exclusion detection, BR progress, and program requirement tracking |
| **Skill workflow** | Reusable operating procedure defining how the agent gathers information, checks constraints, and communicates recommendations |
| **Future: MCP** | Planned Model Context Protocol interface for exposing tools to other AI applications |

## Project structure

```
├── data/
│   ├── mock_courses.json       # 95-course catalog (93 calendar_verified)
│   └── mock_programs.json      # ASMAJ1446A program requirements
├── src/
│   └── tools.py                # Data loading and lookup functions
├── tests/
│   └── test_tools.py           # Pytest test suite (13 tests)
├── docs/
│   ├── scenario.md             # Project context and design decisions
│   ├── concept_mapping.md      # Agent architecture mapping
│   └── demo_cases.md           # Evaluation scenarios
└── skills/
    └── course_planning/
        └── SKILL.md            # Agent operating procedure for course planning
```

## Running tests

```bash
python3 -m pytest
```

## Disclaimer

This tool is not a replacement for official academic advising. All course planning decisions should be verified with the UofT Arts & Science Academic Calendar or an academic advisor.
