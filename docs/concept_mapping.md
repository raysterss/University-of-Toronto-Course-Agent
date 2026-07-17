# Agent Architecture Mapping

This document describes the architectural design choices behind the UofT Course Planning Agent — an AI agent engineering project for helping University of Toronto Cognitive Science students with course planning.

---

## ReAct-Style Reasoning

The agent follows a ReAct (Reasoning + Acting) pattern to handle course planning requests step by step:

1. **Reason**: Analyze the student's request to determine the planning task type (program requirements, approved pool, BR summary, prerequisite check, term availability).
2. **Act**: Call the appropriate tool (course lookup, prerequisite checker, BR summarizer, program requirement checker). When encountering complex prerequisites (indicated by `prerequisite_note`), return `manual_review_needed` rather than overclaiming eligibility.
3. **Observe**: Read tool results, including calendar-verified data, UNKNOWN markers, CSC program restriction notes, and complex prerequisite warnings.
4. **Answer**: Synthesize observations into a clear recommendation, separating verified information from uncertain information and surfacing any `manual_review_needed` statuses.

This pattern was chosen because course planning is inherently multi-step: a single question like "what should I take next term?" requires understanding the student's program, checking completed courses against requirements, verifying prerequisites chains, and cross-referencing term availability — a natural fit for the reason-act-observe loop.

---

## Retrieval: Structured Knowledge Base

The agent retrieves course and program information from structured data files before generating responses:

- `data/mock_courses.json`: Course catalog with 95 entries sourced from the UofT Arts & Science Academic Calendar. 93 courses are `calendar_verified`; 2 courses (MAT137Y1, MAT157Y1) remain `needs_official_verification` because they appear in the ASMAJ1446A program requirements but were not found in the current Academic Calendar and may have been retired.
- `data/mock_programs.json`: Program requirements for ASMAJ1446A (Cognitive Science Major — Science, Computational Cognition Stream), structured into first-year, second-year, upper-year, pool, and capstone sections with choice groups preserving official calendar expressions.

The catalog includes detailed metadata: titles, descriptions, prerequisites (with `prerequisite_note` for complex expressions), exclusions, Breadth Requirement codes, verification status, and program restriction notes. Many upper-year courses have multi-component prerequisites stored in `prerequisite_note` that require `manual_review_needed` rather than simple yes/no eligibility checks.

### Future: RAG / Elasticsearch

A future extension could add Elasticsearch-based retrieval for faster semantic search across larger datasets. This would enable:

- Fuzzy course search by topic, interest, or keyword
- Similarity-based recommendations across departments
- Scalable retrieval if the catalog grows to include the full UofT course offerings

The current MVP uses in-memory lookup from JSON files, which is sufficient for the ~100 course Computational Cognition Stream scope.

---

## Tools: Deterministic Course Planning Functions

The agent uses specialized tools — implemented as deterministic Python functions — to answer course planning questions:

| Tool | Purpose |
|---|---|
| `search_courses` | Look up courses by code, department, level, BR category, or keyword |
| `check_prerequisites` | Verify whether completed courses satisfy a course's prerequisites, returning `manual_review_needed` for complex prerequisite expressions |
| `check_exclusions` | Detect conflicts between completed courses and a target course |
| `check_corequisites` | Identify corequisite requirements for a course |
| `check_term_availability` | Check whether a course is offered in Fall, Winter, or both |
| `summarize_br_progress` | Generate a BR progress table from a list of completed courses |
| `check_program_requirement` | Determine whether a course satisfies a specific program requirement |
| `identify_missing_program_requirements` | Compare completed courses against program requirements (required courses, choice groups, approved pools) |
| `recommend_courses` | Orchestrate multiple checks to produce ranked recommendations |

Each tool is designed to be callable independently, making them composable in different agent workflows and testable in isolation.

---

## Future: MCP (Model Context Protocol)

A planned extension is exposing course-planning tools as an MCP server. This would enable:

- Other AI applications to call the same course-planning functions
- Standardized tool interfaces that work across different MCP-compatible clients
- Separation of the tool implementation from the agent logic

The current MVP calls tool functions directly within the agent. An MCP layer would add an abstraction that makes the tools reusable across different agent frameworks and frontends.

---

## SKILL: Reusable Workflow Instructions

The course planning skill (`skills/course_planning/SKILL.md`) defines a reusable operating procedure for the agent — an "instruction manual" that standardizes how course planning advice is given:

1. What to ask the student if information is missing
2. How to identify the relevant program and stream
3. What order to perform tool calls in
4. How to separate verified from unverified data
5. How to handle complex prerequisites and program restrictions
6. What disclaimers to include in every response

The skill separates the *process* (how to reason about course planning) from the *data* (what courses and programs exist). This makes the workflow reusable across different programs or catalogs by swapping the data while keeping the reasoning structure.

---

## Agent: Model + Tools + Context + Skill

The complete agent combines four components:

| Component | Role |
|---|---|
| **Model** | The LLM that reasons about the student's request and generates responses |
| **Tools** | Deterministic functions that look up course data, check constraints, and summarize progress |
| **Context** | Retrieved course catalog entries and program requirement structures from the knowledge base |
| **Skill** | Workflow instructions that guide the agent's reasoning process and enforce safety boundaries |

### Safety boundaries

The agent does not make decisions for the student. It provides structured information and reasoning, leaving the final enrollment decision to the student and their academic advisor. Key safety measures include:

- `manual_review_needed` for complex prerequisites rather than overclaiming eligibility
- Clear separation of `calendar_verified` data from `needs_official_verification`
- Surfacing CSC program restrictions and UNKNOWN fields rather than guessing
- A mandatory official-source verification reminder in every response
