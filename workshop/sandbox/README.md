# 🧪 The Jev Sandbox

Build **any** Jev request in your browser and see every answer as a widget.

```bash
python sandbox/server.py            # opens http://localhost:8010/
```

| Input (left) | Output (right) |
|---|---|
| **State**: text, or a JSON object (shown as a tree) | **yes/no** (`noul`): a gauge, NO on the left, YES on the right |
| **Questions**: `+ yes/no`, `+ choice`, `+ score`, as many as you like | **choice**: every label's probability, the winner with a trophy |
| yes/no: what YES and NO mean (optional) | **score**: a scale from the lowest level to the highest, with a bar per level |
| choice: labels and what they mean | the model, the tokens, the cost and the time of the call |
| score: the levels, lowest first | |

- **▶ ASK JEV** sends it (one call, all the questions). **Ask 5×** sends the same 5 times: the dots under
  every widget show how much Jev's answers move between two identical calls.
- **The JSON**: the exact request (POST `/v1/systemone`) and response. Paste a request and press **Load into
  the form** to keep working on it with the widgets.
- **History**: every call, with its tokens and cost. Click one to bring it back.
- **Templates**: examples, and YOUR questions from Levels 1-4 (from your code, when it loads).

The form tells you what is missing before it can send (a question without an id, a choice with one label, …).
Your key stays on your computer: the page asks this server, this server asks Jev. `JEV_MOCK=1` works too.
