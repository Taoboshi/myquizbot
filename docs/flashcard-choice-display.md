# Flashcard Choice Display

Flashcards now show all stored options when a question contains multiple
options. Single-answer cards stay as direct question/answer pairs. Existing
complete lists in question text are not appended again. Source option arrays,
correct indices and test ordering are unchanged.

## Biology Module 5 Import Repairs

Verified against the user's original text attachment
`7235a60e-2b64-4d2c-82a1-0a03461145d2/Вставленный текст.txt`.

- Card 6: restored the full list to the front and the explicit source answer
  `все ответы правильные` to the reverse.
- Cards 13, 33, 39 and 110: restored the last list item to the front. These
  source blocks have no separately marked answer. The reverse explicitly says
  that the source does not specify the correct answer and clarification is
  needed, rather than falsely claiming that the final list item is the answer.

These four cards require source-author clarification before a correct key can
be supplied. No medical/biological answer keys were inferred or invented.
All 385 card positions are retained to avoid shifting saved progress IDs.
