# Course Planning Skill

This skill defines the agent's internal operating procedure for course planning. It standardizes how the UofT Course Planning Agent gathers information, checks constraints, handles uncertainty, and communicates recommendations when a student asks for help planning their Cognitive Science Computational Cognition Stream coursework.

---

## Step 1: Gather Missing Information

If the student has not provided all necessary information, ask for it:

- **Completed courses**: Ask the student to list all courses they have completed.
- **Program and stream**: Confirm the student's program (default: Cognitive Science Major — Science, Computational Cognition Stream, ASMAJ1446A).
- **Target term**: Ask which term the student is planning for (Fall, Winter, or both).
- **Planning need**: Clarify what the student wants (program requirements, approved pool, BR summary, prerequisite check, or general exploration).

Do not proceed until you have enough information to give a useful answer.

---

## Step 2: Identify the Task Type

Determine which planning task the student is asking about:

| Task Type | Description |
|---|---|
| Program requirement planning | Which courses satisfy required courses, choice groups, or approved pools? |
| Approved course pool selection | Which courses are in the Computational Cognition Stream pool? |
| Breadth Requirement summary | What BR categories are covered or still needed? |
| Prerequisite eligibility | Can the student take a specific course? |
| Term availability | Is a course offered in the target term? |
| General exploration | Interest-based exploration outside program constraints. |

---

## Step 3: Look Up Program Requirements

For program-related questions, load the program data for ASMAJ1446A. Check:

1. **Required courses**: COG100H1, COG200H1, PSY270H1, PSY290H1, PHL342H1.
2. **Choice groups**:
   - `intro_cs_pathway` — completion logic: complete one full option.
   - `math_pathway` — completion logic: complete one full option.
   - `statistics_choice` — completion logic: complete one full option.
   - `capstone_choice` — completion logic: complete one full option.
3. **Approved pools**: Computational Cognition Stream pool (2.5 credits needed).
4. **Special rules**:
   - At least 1.0 credit at 300-level or higher from the pool.
   - No more than 1.5 credits from any single 3-letter designator, except CSC.
   - CSC courses: minimum 1.0 credit and up to 2.0 credits.

When evaluating choice groups, do not only sum credits. Check whether one full option is completed. Use the `completion_logic` field to guide this evaluation.

---

## Step 4: Check Course Constraints

For each course being considered, check:

1. **Prerequisites**: Are all prerequisites in the student's completed courses list?
   - First, check the simple `prerequisites` list.
   - If the course has a non-empty `prerequisite_note`, the prerequisite logic is complex. Do not rely only on the simple list.
   - Complex prerequisites include: OR conditions (multiple accepted courses for one requirement), grade thresholds (minimum grade in a prerequisite), and multi-component requirements (multiple independent prerequisites that must all be satisfied).
   - For complex prerequisites, return a status of **"manual_review_needed"** and explain:
     - What the prerequisite_note says (quote or paraphrase).
     - Which pathways or conditions the student must satisfy.
     - Whether grade thresholds apply.
     - That the student should verify eligibility with the official Academic Calendar or academic advising.
2. **Corequisites**: Does the student need to take a corequisite concurrently? If `corequisite_note` is present, the corequisite logic is complex and should be surfaced similarly.
3. **Exclusions**: Has the student already taken a course listed in the exclusions? If so, the course may not count toward degree requirements.
4. **CSC program restrictions**: For 300-/400-level CSC courses, check for program restriction notes in `verification_note`. Surface the 1.5-credit cap for students not enrolled in CS Major/Specialist or Data Science Specialist.
5. **Breadth Requirement**: What BR category does the course provide?
6. **Term availability**: Is the course offered in the target term? If UNKNOWN, tell the student.

Report any issues clearly. If prerequisites are missing, tell the student what they still need to complete. If prerequisites are complex, explain the options rather than giving a simple yes/no.

---

## Step 5: Separate Verified from Unverified Data

Always check the `verification_status` field on course and program data:

- `calendar_verified`: Data was confirmed against the UofT Academic Calendar. Present this as reliable information. 93 of 95 courses in the catalog have this status.
- `needs_official_verification`: Data could not be confirmed. Present with the phrase "needs official verification." Currently only MAT137Y1 and MAT157Y1 have this status — they appear in the ASMAJ1446A program requirements but were not found in the current Academic Calendar and may have been retired. Students should verify these pathway options with the official calendar or academic advising.

### UNKNOWN values

Some courses have `breadth_code: "UNKNOWN"` or `term_availability: ["UNKNOWN"]`. These are accurate representations of the Academic Calendar data — the Calendar either does not list the information or it could not be confirmed. Do not guess or fill in UNKNOWN fields. State them clearly:

- "BR: not listed on the Academic Calendar page"
- "Term availability: not yet verified from official timetable"

A small number of courses have UNKNOWN breadth because the Calendar does not list BR for them (e.g., independent study courses COG497Y1, COG498H1, COG499H1; and LIN232H1, PSY330H1 where BR is absent from the calendar entry).

---

## Step 6: Recommend and Explain

When recommending courses:

1. Prioritize courses that satisfy outstanding program requirements.
2. Explain why each course is recommended (required, choice group, pool, or BR need).
3. Mention any risks, such as UNKNOWN term availability, missing prerequisite chains, or exclusion concerns.
4. For upper-year CSC courses (300-/400-level), also include:
   - Whether the course counts toward the Computational Cognition Stream pool.
   - Known prerequisite information, including whether prerequisites are complex (prerequisite_note present).
   - Any complex prerequisite warning with "manual_review_needed" status.
   - Any CSC program restriction note (1.5-credit cap for non-CS-major students).
   - Verification status.
   - A reminder to verify final eligibility with official sources.
5. Recommend 2–3 courses maximum unless the student asks for more.
6. Include: course code, title, requirement category, prerequisite status (including "manual_review_needed" if complex), corequisite awareness, exclusion status, CSC program restriction if applicable, term availability, BR category (or UNKNOWN), verification status, match reason, and possible risks.

---

## Step 7: Close with Verification Reminder

Always end with a reminder similar to:

> "This information is based on mock data and UofT Academic Calendar data where available. Some fields may be unverified or simplified. Please verify all requirements with the official UofT Arts & Science Calendar or your academic advisor before making enrollment decisions."

---

## What This Skill Must Never Do

- Invent official UofT requirements that are not in the data.
- Present unverified data as confirmed.
- Claim that a course is guaranteed to satisfy a degree requirement.
- Claim that a student has officially completed their Breadth Requirement.
- Replace an academic advisor.
- Make final enrollment decisions for the student.
- Simplify complex prerequisite expressions (OR conditions, grade thresholds, multi-component requirements) into a simple yes/no eligibility answer unless the course data clearly supports it.
- Claim that a student is within or over the CSC 300-/400-level credit cap without complete enrollment data.
