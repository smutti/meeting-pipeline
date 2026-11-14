---
name: meeting-review
description: "Review issues in an existing meet job: compare readings, confirm speakers and apply corrections with audio alignment. Use for a processed local pipeline job or review report."
---

# Meeting Review

Use `meet` from PATH or `~/.local/bin/meet`. Find the job with `meet jobs`; inspect `meet review list JOB --limit 20` and its report. Read only the relevant local artifacts. Prioritize speaker identity questions and disagreements involving names, numbers, negation or commitments.

Show a few concise decisions at a time, with timestamp and alternatives. A third reading is additional evidence, not ground truth. Do not claim to have heard an audio clip unless it was actually listened to. The user can listen in the generated local HTML report.

Apply a confirmed choice with:

```sh
meet review resolve JOB ISSUE --action keep
meet review resolve JOB ISSUE --action name --name "Confirmed person"
meet review resolve JOB ISSUE --action replace --text "Confirmed spoken text" --language it
```

`keep` confirms the current selection for that issue. `name` maps the speaker across this meeting; it does not enroll a persistent voice profile. `replace` requires a local aligner and an unambiguous language; preserve the timing of unchanged words and let the engine align the replacement. Do not edit generated JSON or reuse old timestamps for new words. Conflicting overlapping replacements must be resolved against the current reviewed text.

Use `meet review render JOB` to refresh files. Report remaining open items. Export through `meet export` only to a destination in the user's task; use `--draft` when unresolved output is intentionally wanted.
