# UofT Course Planning Agent

## Project goal

This is an AI agent engineering project exploring how a course-planning agent can help University of Toronto students in the **Cognitive Science Major — Science Program, Computational Cognition Stream** (ASMAJ1446A).

The agent helps a student reason about possible course choices within the specific academic constraints of this program.

The main goal is not to randomly recommend interesting courses.

The main goal is to help the student understand:

- which courses may satisfy program requirements
- which courses are required
- which courses belong to approved course pools (especially the Computational Cognition Stream pool)
- whether prerequisites appear to be satisfied
- whether corequisites are needed
- whether exclusions may create issues
- whether courses are offered in a target term
- what Breadth Requirement areas the student has already covered
- what Breadth Requirement areas may still be missing
- which choice groups (pathways) still need to be completed

The project uses UofT Academic Calendar data when available. Unverified data must be clearly marked.

## Data sources and verification

Course and program data is sourced from the UofT Arts & Science Academic Calendar. The course catalog contains 95 courses, of which 93 are `calendar_verified`. Two courses (MAT137Y1, MAT157Y1) remain `needs_official_verification` — they appear in the official ASMAJ1446A program requirements but were not found in the current Academic Calendar and may have been retired or reorganized into newer course sequences. Each course entry includes a `verification_status` field:

- `calendar_verified`: Data was confirmed against the official Academic Calendar.
- `needs_official_verification`: Data could not be confirmed. Currently only MAT137Y1 and MAT157Y1. Should be treated as uncertain.

A small number of courses have `breadth_code: "UNKNOWN"` because the Academic Calendar page does not list a Breadth Requirement (e.g., independent study courses COG497Y1/COG498H1/COG499H1, and some courses where BR is simply absent from the calendar entry such as LIN232H1 and PSY330H1). UNKNOWN breadth is accurate — not an error — and the agent should state it clearly rather than guessing.

Many 300-/400-level courses have complex prerequisite expressions stored in `prerequisite_note`. Tools and the agent must return `manual_review_needed` for these rather than overclaiming eligibility.

The agent must:

- Use calendar-verified data as the primary source of truth.
- Clearly separate verified information from uncertain information.
- Use phrases like "needs official verification" when data is uncertain (currently only MAT137Y1 and MAT157Y1).
- Never invent official UofT requirements.
- Never claim that a recommendation is officially guaranteed.
- Remind students that this tool is not a replacement for official academic advising.

## Core course planning problem

UofT course planning is difficult because students often need to satisfy multiple constraints at the same time.

A student may need to know:

- which courses are required for their program
- which courses can be selected from an approved course pool
- whether they satisfy prerequisites
- whether a course has corequisites
- whether a course has exclusions
- whether a course contributes to a Breadth Requirement category
- whether a course is offered in Fall, Winter, or both
- whether delaying a course may cause planning problems later
- whether special program rules (e.g., department credit caps) are satisfied

This project models those problems using real program requirements from the UofT Academic Calendar, with course data verified against the calendar where possible.

## Target user

The target user is a University of Toronto undergraduate student enrolled in or considering the **Cognitive Science Major — Science Program, Computational Cognition Stream** (ASMAJ1446A).

Example student profile:

- third-year student
- enrolled in the Cognitive Science Major — Science (Computational Cognition Stream)
- has completed some introductory cognitive science, programming, and calculus courses
- needs to satisfy program requirements including required courses and choice groups
- needs to choose from the Computational Cognition Stream approved pool
- wants to understand Breadth Requirement progress
- wants to avoid courses where prerequisites are not satisfied
- wants to know whether courses are available in a target term

## Example user request

A student may ask:

"I am a third-year UofT student in the Cognitive Science Major — Computational Cognition Stream. I have completed COG100H1, CSC108H1, and MAT135H1. I need to choose courses for next term. What should I take to stay on track with my program requirements?"

Another student may ask:

"Here is a list of all the courses I have taken. Can you summarize which Breadth Requirement categories I have already covered and which ones I still need?"

Another student may ask:

"I have completed COG100H1, PSY270H1, and CSC148H1. Can I take CSC384H1 next Winter? What prerequisites am I still missing?"

## Planning priority

The agent should first understand what type of planning task the user is asking about.

Common task types include:

1. program requirement planning
2. approved course pool selection (Computational Cognition Stream pool)
3. Breadth Requirement summary
4. prerequisite eligibility checking
5. term availability checking
6. choice group completion tracking
7. general interest-based elective exploration

When the user asks about program requirements or an approved course pool, the agent should prioritize courses that belong to the relevant required category or approved pool.

When the user explicitly asks about general electives or interest-based courses outside the program requirement context, the agent may consider courses outside the approved program pool.

In other words, course pools should guide recommendations when the user is trying to satisfy a requirement, but they should not permanently block all broader exploration.

## Program-specific reasoning

The agent should understand the structure of the Cognitive Science Major — Computational Cognition Stream:

- **Required courses**: COG100H1, COG200H1, PSY270H1, PSY290H1, PHL342H1
- **Choice groups**: intro CS pathway, math pathway, statistics choice, capstone choice
- **Approved pool**: Computational Cognition Stream (2.5 credits, with department-level rules)
- **Special rules**: CSC credit range (1.0–2.0), 300-level minimum, designator caps

The agent should reason about these structures when evaluating a student's progress and making recommendations.

## Complex prerequisites and prerequisite notes

Many courses in the Computational Cognition Stream pool — especially 300-/400-level CSC courses — have prerequisites that cannot be reduced to a simple flat list of course codes. The course catalog captures this complexity through metadata fields:

- `prerequisite_note`: A human-readable summary of the official prerequisite expression, used when prerequisites involve OR conditions, grade thresholds, multi-component requirements (AND of two or three separate requirements), or multiple accepted pathways.
- `corequisite_note`: Similar to prerequisite_note but for corequisites.
- `prerequisite_expression`: A raw or paraphrased version of the official calendar prerequisite text, used when the expression is too complex for the simple `prerequisites` list.

### When prerequisites are complex

If a course has a non-empty `prerequisite_note`, tools and the agent must not claim that the student is definitely eligible based only on the simple `prerequisites` list.

Instead, the agent should communicate a status like:

**"manual_review_needed"**

This means the prerequisite logic involves conditions that cannot be automatically resolved from a flat list of completed course codes alone. The agent should:

1. Quote or paraphrase the `prerequisite_note` or `prerequisite_expression`.
2. Explain what the student would need to satisfy (e.g., which pathways exist).
3. Recommend that the student verify eligibility with the official Academic Calendar or academic advising.

The agent must not simplify a complex prerequisite into a definite yes/no answer unless the course data clearly supports it.

### Grade thresholds

Some courses require a minimum grade in a prerequisite course (e.g., MAT136H1 with 77%+, CSC110Y1 with 70%+). When the catalog records a grade threshold in the `prerequisite_note`, the agent must surface it. If the student has not provided grade information, the agent should note that grade thresholds apply and ask the student to check.

### Multi-component prerequisites

Some courses require multiple independent components to be satisfied simultaneously. For example, CSC303H1 requires:

1. An algorithms course (CSC263H1 or equivalent)
2. A statistics course (STA237H1/STA247H1/STA255H1/STA257H1 or equivalent)
3. A linear algebra course (MAT223H1 or equivalent)

All three components must be met. The agent should evaluate each component separately and report the overall status.

## CSC program restrictions for 300-/400-level courses

The UofT Academic Calendar includes a restriction on upper-year CSC/ECE courses:

> "Students not enrolled in the Computer Science Major or Specialist program at A&S, UTM, or UTSC, or the Data Science Specialist at A&S, are limited to a maximum of 1.5 credits in 300-/400-level CSC/ECE courses."

This restriction applies to many CSC courses in the Computational Cognition Stream pool. The catalog records this in the `verification_note` field where applicable.

Cognitive Science students who are not also enrolled in a Computer Science Major/Specialist or Data Science Specialist must track their 300-/400-level CSC credits against this 1.5-credit cap.

### What the agent should do with program restrictions

When recommending or evaluating a 300-/400-level CSC course:

1. Check whether the course entry includes a program restriction note.
2. If it does, surface the restriction to the student.
3. Note that the 1.5-credit cap applies across all 300-/400-level CSC courses taken.
4. Remind the student to verify their eligibility with the official Academic Calendar or academic advising.
5. Do not claim that the student is definitely within or over the cap without complete enrollment data.

This is especially important for the Computational Cognition Stream pool because the pool already requires 2.5 credits from the pool, and the special rules require at least 1.0 credit of CSC courses (and up to 2.0). Students must balance pool requirements against the non-CS-major CSC credit cap.

## Breadth Requirement support

The agent should support a Breadth Requirement workflow.

When the user wants BR help, the agent should ask the user to provide all completed courses.

For each completed course, the agent should look up the course's BR category in the course catalog.

Then the agent should summarize the student's current BR progress in a table.

The table should show:

- BR category
- completed courses in that category
- total credits counted in that category
- whether the category appears complete, partially complete, or missing

The agent should also explain which BR categories may still need attention.

When recommending future courses, the agent should include each course's BR category if available. If a BR category is UNKNOWN, the agent should clearly state that.

The agent should not claim official BR completion. It should remind the user to verify with official UofT sources.

## Simplified term availability support

The MVP includes simple term availability.

Examples:

- offered in Fall
- offered in Winter
- offered in both Fall and Winter
- UNKNOWN (not yet verified from official timetable)

The MVP does not need to check exact lecture, tutorial, or practical time conflicts.

This keeps the project manageable while still representing a real course planning pain point.

## What the agent should do

The agent should:

1. Understand the student's program, completed courses, target term, and planning need.
2. Identify whether the user is asking about program requirements, approved course pools, BR progress, prerequisites, term availability, or general interests.
3. Search the course catalog for relevant courses.
4. Check whether each course belongs to the relevant requirement category or approved course pool when applicable.
5. Check whether prerequisites appear to be satisfied.
   - If the course has a `prerequisite_note`, evaluate whether the simple `prerequisites` list is sufficient. If the prerequisite logic is complex (OR conditions, grade thresholds, multi-component requirements), return a status of "manual_review_needed" and explain why.
6. Check whether corequisites are needed.
7. Check whether exclusions create a possible issue.
8. Check for CSC program restrictions on 300-/400-level courses and surface them when relevant.
9. Check whether the course is available in the target term.
10. Include Breadth Requirement information when available.
11. Recommend a small number of suitable courses when the user asks for recommendations.
12. For upper-year CSC course recommendations, include: whether the course counts toward the Computational Cognition Stream pool; known prerequisite information; any complex prerequisite warning; any program restriction note; verification status; and a reminder to verify final eligibility with official sources.
13. Explain why each course is recommended, referencing program requirements where relevant.
14. Clearly mark uncertain or unverified data.
15. Mention risks, missing information, or assumptions.
16. Remind the student to verify official requirements using UofT sources.

## What the agent should not do

The agent should not:

- claim that a course is officially guaranteed to satisfy a degree requirement
- claim that a student has officially completed their Breadth Requirement
- replace an academic advisor
- rely on hallucinated course information
- invent prerequisites that are not in the data
- invent BR categories that are not in the data
- treat interest-based recommendations as program requirement recommendations
- make final enrollment decisions for the student
- build a full timetable with exact lecture/tutorial conflicts in the MVP
- present unverified data as if it were confirmed
- simplify complex prerequisite expressions (OR conditions, grade thresholds, multi-component requirements) into a simple yes/no eligibility answer unless the data clearly supports it
- claim that a student is within or over the CSC 300-/400-level credit cap without complete enrollment data

## MVP scope

The MVP should support:

- a course catalog aligned with the Cognitive Science Computational Cognition Stream
- program requirement data from the UofT Academic Calendar (ASMAJ1446A)
- required course labels
- approved course pool labels (Computational Cognition Stream)
- choice group evaluation (pathways, statistics, capstone)
- prerequisite checking against a list of completed courses
- corequisite awareness
- exclusion warnings
- Breadth Requirement tags
- BR progress summary from completed courses
- term availability checking, such as Fall-only or Winter-only
- clear separation of verified vs. unverified data
- simple recommendation output
- a course planning skill that defines the reasoning workflow

The MVP does not need to support:

- full timetable conflict solving
- workload ranking
- live UofT course data
- official degree audit
- automatic enrollment planning

## Later extensions

Later versions may add:

- Elasticsearch-based retrieval
- MCP tool exposure
- real UofT course data
- exact timetable conflict checking
- multi-year course planning
- official degree requirement tracking
- richer ReAct loop visibility
- integration with official timetable or calendar data

## Success criteria

The demo is successful if the agent can answer questions like:

"Given my completed courses, program requirements, and target term, recommend 2-3 possible courses and explain the reasoning."

The answer should include:

- course code
- course title
- requirement category if applicable
- whether it is required, from an approved course pool, or a general elective
- prerequisite status (including "manual_review_needed" if the prerequisite expression is complex)
- if prerequisites are complex, quote or paraphrase the prerequisite_note and explain which pathways or conditions apply
- corequisite awareness if relevant
- exclusion warning if relevant
- CSC program restriction note if the course is 300-/400-level CSC
- term availability
- Breadth Requirement category if available (or UNKNOWN)
- verification status of the data used
- match reason
- possible risk
- official verification reminder

The demo is also successful if the agent can answer:

"Here are all the courses I have completed. Can you summarize my Breadth Requirement progress?"

The answer should include a BR table and explain what appears complete or missing based on the available data, while clearly noting any UNKNOWN BR values.