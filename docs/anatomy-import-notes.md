# Anatomy PDF Import

Four Quizlet PDF exports were imported as tests with flashcard support.
Original answer choices and answer keys were retained. Obvious missing spaces
and line-wrap artifacts were normalized without changing the answer keys.

## Incomplete Source Entry

Source: `a2f217b0-ba8a-470d-91ea-f1edf54d8267.pdf`, page 62, question 196.
The source contains only the instruction to choose one answer, with no question
prompt. This entry was excluded from the active test until the prompt is supplied.

Original options:

- a. pulpa dentis
- b. periodontium
- c. enamelum
- d. cementum
- e. dentinum

Source answer: d. cementum.

Final counts: musculoskeletal 223, urogenital 240,
digestive/respiratory 294, cardiovascular 225 (982 total).

Tests are imported as unassigned so an administrator can attach them to the
existing anatomy subject without creating a duplicate subject.

## Second Batch

Added osteology (318), cranial nerves (234), spinal/autonomic nerves (104),
central nervous system (251), and spinal nerves (160): 1067 questions total.

The following ambiguous source answer keys were excluded rather than guessed:

- Osteology, source question 126: `d. борозда поперечного синуса b. затылочный мыщелок`.
- Osteology, source question 248: `e. раковинный гребень d. передний слезный гребень`.
- Central nervous system, source question 28: `a. двигательные парасимпатические c. двигательные соматические`.

In cranial nerves questions 128, 154, 228 and CNS question 7, the answer option
missing from the question column was restored from the explicitly lettered
answer column. Spinal nerves question 140 repeats the same answer twice;
the duplicate was removed. No answer keys were medically reinterpreted.

## Comprehensive Exam

Source: `Карточки анат 1000 вопросов док _ Quizlet.pdf`.
The source advertises 1021 terms, and all 1021 were imported into
`anatomy_comprehensive`. Numeric source answer keys were converted to zero-based
indices. Source option separators in entries 39 and 578 were restored from
embedded separator characters. All source options are retained in flashcards
as well as in the test. No medical answer-key corrections were applied.
