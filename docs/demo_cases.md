# Evaluation Scenarios

This document defines evaluation scenarios for the UofT Course Planning Agent — an AI agent engineering project for ASMAJ1446A course planning. Each scenario describes a realistic student situation, the expected agent behavior, and success criteria for measuring agent performance.

---

## Scenario 1: Next Steps After First-Year Courses

**Student scenario**:
> "I am in the Cognitive Science Major — Computational Cognition Stream. I have completed COG100H1, CSC108H1, and MAT135H1. What should I take next to stay on track?"

**Agent should**:
1. Identify the program (ASMAJ1446A) from context or ask the student.
2. Look up completed courses in the catalog.
3. Identify what is still missing from required courses, choice groups, and the Computational Cognition pool.
4. Check prerequisite chains: COG100H1 → COG200H1, CSC108H1 → CSC148H1, MAT135H1 → MAT136H1.
5. Recommend next-term courses (e.g., COG200H1, CSC148H1, MAT136H1) with reasoning.
6. Note any BR categories covered and still needed.
7. Include verification status and official-source reminder.

**Success criteria**:
- Recommends COG200H1 (prerequisite satisfied), CSC148H1 (prerequisite satisfied), MAT136H1 (prerequisite satisfied).
- Explains that these complete the CS pathway and math pathway choice groups.
- Mentions that PSY270H1, PSY290H1, and PHL342H1 are also required but may be taken in later years.
- Notes that STA237H1 requires MAT136H1 as a prerequisite.

---

## Scenario 2: Complex Prerequisite Check for CSC384H1

**Student scenario**:
> "I have completed COG100H1, PSY270H1, CSC148H1, and STA237H1. Can I take CSC384H1 next Winter?"

**Agent should**:
1. Look up CSC384H1. Note the `prerequisite_note`: the official prerequisites (CSC263H1, STA237H1) are in the simple `prerequisites` list, but STA237H1 itself has a complex `prerequisite_note` with multiple calculus pathway options.
2. Check: STA237H1 is completed ✓. CSC263H1 is missing.
3. Note that many 300-/400-level CSC courses have a program restriction: non-CS-major students are limited to 1.5 credits in 300-/400-level CSC/ECE courses.
4. Return a prerequisite status of `manual_review_needed` for the full chain since STA237H1's own prereqs involve multiple calculus pathway options.
5. Explain what courses the student would still need to take.
6. Include verification status and official-source reminder.

**Success criteria**:
- Clearly states CSC384H1 is not yet available (CSC263H1 missing).
- Notes that STA237H1's prerequisites are complex and the eligibility chain should be manually reviewed.
- Warns about the CSC 300-/400-level credit cap for non-CS-major students.
- Maps the remaining prerequisite chain: CSC263H1 requires CSC207H1 (requires CSC148H1 ✓).
- Notes that CSC384H1 is a Computational Cognition Stream pool course, BR5, and Winter-only.

---

## Scenario 3: Pool Courses That Also Satisfy BR5

**Student scenario**:
> "Which Computational Cognition Stream pool courses also count toward BR5? I still need BR5 credits."

**Agent should**:
1. Look up all courses tagged with `computational_cognition_stream_pool`.
2. Filter by `breadth_code: "BR5"`.
3. Present the matching courses.
4. For each match, include prerequisite requirements, term availability, and verification status.
5. Clearly separate verified BR values from UNKNOWN ones.
6. Note the special pool rules (CSC credit range, 300-level minimum, designator caps).

**Success criteria**:
- Lists BR5 pool courses (e.g., CSC311H1, CSC384H1, CSC165H1, CSC207H1, CSC320H1, CSC324H1, CSC412H1, COG403H1, COG260H1, CSC413H1, CSC420H1, CSC485H1, CSC486H1, LIN323H1, PSY305H1, BPM438H1, PHY359H1 — the catalog now has 95 courses with verified BR values).
- Indicates which have calendar-verified BR values (all pool courses are now verified).
- Flags any pool courses where BR is UNKNOWN (e.g., LIN232H1, PSY330H1 — BR not listed on Calendar page).
- Notes that independent study courses (COG497Y1, COG498H1, COG499H1) also have UNKNOWN breadth.
- Reminds about the special rule: CSC courses require 1.0–2.0 credits from the pool.

---

## Scenario 4: Exclusion Warning

**Student scenario**:
> "I took PSY201H1. Is STA238H1 still useful for me, or does the exclusion mean I cannot count it?"

**Agent should**:
1. Look up STA238H1 exclusions — PSY201H1 is listed.
2. Look up PSY201H1 exclusions — STA238H1 is listed.
3. Explain that taking both means one would be an extra course (not counted toward degree requirements).
4. Check the program's statistics choice group: only one statistics course is needed.
5. Conclude that STA238H1 would not add value for program requirements since PSY201H1 already satisfies the statistics choice.
6. Recommend alternative courses if the student needs more credits.
7. Include verification status.

**Success criteria**:
- Clearly identifies the mutual exclusion between PSY201H1 and STA238H1.
- Explains that both cannot count toward the statistics requirement.
- Notes that PSY201H1 already satisfies the `statistics_choice` requirement.
- Suggests the student focus on other requirements instead.

---

## Scenario 5: Fall/Winter Planning with UNKNOWN Term Availability

**Student scenario**:
> "I need to plan my Fall and Winter courses. I still need to complete: the Computational Cognition pool (2.5 credits) and the capstone requirement. What are my options?"

**Agent should**:
1. List pool courses and capstone courses with their known term availability.
2. For courses where term availability is UNKNOWN, clearly state that.
3. Separate courses into "confirmed for Fall," "confirmed for Winter," "available both terms," and "UNKNOWN."
4. Recommend a plan using confirmed-term courses where possible.
5. For UNKNOWN-term courses, suggest the student check the official timetable.
6. Check prerequisites for all recommended courses.
7. Verify special rules (CSC credit range, 300-level minimum, designator caps).
8. Include verification status and official-source reminder.

**Success criteria**:
- Organizes options by term availability with UNKNOWN clearly separated.
- Recommends a feasible Fall/Winter split using confirmed-term courses.
- Flags which recommendations depend on UNKNOWN data.
- Suggests the student check the official UofT timetable for UNKNOWN courses.
- Verifies that the recommended plan satisfies the special pool rules.

---

## General Success Criteria for All Scenarios

Every agent response should include:

- Course codes and titles for all referenced courses.
- Verification status of the data used (93 of 95 courses are now `calendar_verified`; MAT137Y1 and MAT157Y1 remain `needs_official_verification`).
- Clear separation of calendar-verified data from uncertain data.
- For complex prerequisites (indicated by `prerequisite_note`), a `manual_review_needed` status explaining which pathways or conditions apply.
- For 300-/400-level CSC courses, the program restriction note about the 1.5-credit cap for non-CS-major students.
- A reminder to verify with official UofT sources.
- The standard disclaimer: "This project is not a replacement for official academic advising."
- No invented requirements or hallucinated course information.
