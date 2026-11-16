# Adjudication sheet

`ai_adjudication_sheet.jsonl` holds the 8 AI observations produced on 12 real public PRs (2026-11-16, Groq `openai/gpt-oss-120b`). Each line is one finding with `label: null`.

To get a measured precision, a person who knows the code sets each `label` to `"true_positive"`, `"false_positive"` or `"unsure"` (open the PR and read the changed line). Then compute it:

```python
import json
from lyvern.benchmark.real_prs import precision_from_labels
rows = [json.loads(line) for line in open("docs/benchmark/ai_adjudication_sheet.jsonl", encoding="utf-8")]
confusion, unlabelled = precision_from_labels(rows)
print(confusion.summary(), "| unlabelled:", unlabelled)
```

The code in the findings belongs to the public projects named in the `pr` field; only short single-line quotes are stored here for labelling.
