import re
import requests

OLLAMA_URL = "http://localhost:11434/api/chat"

SYSTEM_PROMPT = """You are a research assistant that answers questions using tools.

You have NO prior knowledge of any fact in the task. Every number must come from a
tool Observation. Never invent, guess, or recall figures from memory. Always begin
with a search.

Respond in exactly one of these two formats.

To use a tool:
Thought: <reasoning>
Action: <search | fetch | calc>
Action Input: <input>

When every number you report has come from an Observation:
Thought: <reasoning>
Final Answer: <answer>

Tools:
- search(query): returns a list of matching documents and their ids
- fetch(doc_id): returns the full text of a document
- calc(expression): evaluates an arithmetic expression

Use one action at a time and wait for the Observation before the next step.

Example (a different task, showing the format only):
Thought: I do not know this; I must look it up.
Action: search
Action Input: tallest mountain
Observation: Results:
- Everest (everest)
Thought: I will read the document.
Action: fetch
Action Input: everest
Observation: Everest. Height: 8849.
Thought: I now have the figure from a tool.
Final Answer: 8849"""

_FINAL = re.compile(r"Final Answer:\s*(.*)", re.S)
_ACTION = re.compile(r"Action:\s*([^\n]+)")
_INPUT = re.compile(r"Action Input:\s*(.*)", re.S)
_NAME = re.compile(r"[a-zA-Z_]+")


def parse(text):
    m = _FINAL.search(text)
    if m:
        return "final", None, m.group(1).strip()
    a = _ACTION.search(text)
    if a:
        name = _NAME.search(a.group(1))
        name = name.group(0) if name else ""
        i = _INPUT.search(text)
        arg = ""
        if i:
            arg = i.group(1).strip().splitlines()[0].strip().strip("`\"'")
        return "action", name, arg
    return "none", None, None


class Agent:
    def __init__(self, model, tools, max_steps=25, temperature=0.0):
        self.model = model
        self.tools = tools
        self.max_steps = max_steps
        self.temperature = temperature

    def _chat(self, messages):
        r = requests.post(OLLAMA_URL, json={
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.temperature},
        }, timeout=600)
        r.raise_for_status()
        return r.json()

    def run(self, task):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ]
        steps = tool_calls = prompt_tokens = completion_tokens = 0
        answer = None
        fetched = False
        trace = []

        while steps < self.max_steps:
            resp = self._chat(messages)
            steps += 1
            prompt_tokens += resp.get("prompt_eval_count", 0)
            completion_tokens += resp.get("eval_count", 0)
            text = resp["message"]["content"]
            kind, name, arg = parse(text)

            if kind == "final" and not fetched:
                trace.append(("rejected_final", arg))
                messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content": (
                    "Observation: You have not read any document yet. The figures are "
                    "inside the documents, not in the search list. Do not answer from "
                    "memory. Use fetch to read each document before answering.")})
                continue

            if kind == "final":
                answer = arg
                trace.append(("final", answer))
                break

            messages.append({"role": "assistant", "content": text})
            if kind == "action" and name in self.tools:
                obs = self.tools[name](arg)
                tool_calls += 1
                if name == "fetch":
                    fetched = True
                trace.append((name, arg))
            elif kind == "action":
                obs = "Unknown tool. Available: search, fetch, calc."
                trace.append(("unknown", name))
            else:
                obs = "Could not parse. Use Action + Action Input, or Final Answer."
                trace.append(("unparsed", None))
            messages.append({"role": "user", "content": "Observation: " + obs})

        return {
            "answer": answer,
            "steps": steps,
            "tool_calls": tool_calls,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "hit_cap": answer is None,
            "trace": trace,
        }
