# Token / Tool-Call Amplification against a ReAct Agent

## Overview

- This report shows a resource-exhaustion attack on an AI agent. A malicious data
  source makes a tool-using agent spend far more tokens and tool calls than a task
  needs, while the final answer stays correct.
- Tokens are the units a language model reads and writes, and every tool call is a
  full model round-trip. More of either means more compute cost, money, and time, so
  driving them up is the attacker's goal.
- The attack works by shaping the data the agent reads, not by injecting instructions
  the model might ignore. Because of that it is reliable across models and carries no
  suspicious text for a filter to catch.
- Setup: a ReAct agent running locally on Ollama with a 3B model. A ReAct agent
  reasons, then acts by calling a tool, reads the result, and repeats until it
  answers. It has three simple tools: search (find documents), fetch (read a
  document), and calc (do arithmetic).
- Task used throughout: find the combined population of three cities. The correct
  answer is always 7,000,000, and every attack keeps that answer correct.

## Threat model

- The attacker controls the tool outputs, meaning the text that search and fetch
  return to the agent.
- This matches a real agent connected to an untrusted or compromised data source,
  such as a poisoned search index or a malicious tool server that the agent trusts.
- The attacker does not control the user's task, the agent's instructions, the tool
  code, or the model itself. Only the data flowing back from the tools.
- The goal is cost, not a wrong answer. The attacker wants to raise tokens and tool
  calls while the answer still looks normal, so nothing downstream notices.
- An attack that corrupts the answer does not count here. A wrong answer is easy to
  catch, so it defeats the point of a quiet, expensive run.
- Why the cost grows so fast: a ReAct agent has no memory of its own, so at every
  step it re-sends the entire conversation so far back to the model.
- This means extra steps do not just add themselves. Each new step carries a longer
  history, so the token count grows much faster than the number of steps.
- Forcing extra tool calls is therefore the strongest lever, because each call adds a
  whole new round-trip on top of an already growing transcript.

## How the inputs were found

- I wrote four attack designs by hand. Then I ran all four the same way, five times
  each, and compared their results in one table to see which amplifies most while
  keeping the answer correct.
- The guiding idea was to make the agent do more work through its own normal logic,
  not by hoping it obeys injected text.
- The real population figures are never changed, so the agent can always reach the
  correct total of 7,000,000. Only the path to it gets longer.
- The four designs:
  - conflict: each figure appears in several disagreeing sources, so the agent has to
    re-read and re-check to decide which to trust.
  - fanout: each city's figure is split across district sub-documents, so the number
    only exists as the sum of several extra fetches.
  - pagination: each figure sits on the last of several pages, so the agent has to
    page through the earlier pages to reach it.
  - prompt_injection: a weak baseline. A hidden instruction block in the data simply
    asks the agent to do extra work. It is included only to contrast with the others.

## Amplification results

- The numbers come from the token counts the model reports on every call (input plus
  output), summed over every step of a run, and averaged over 5 trials on qwen2.5:3b.
- AF (amplification factor) is how many times more an attack costs than a benign run.
  AF 7.3x means 7.3 times the tokens of the benign run (the normal, clean baseline).
- Stealth is the share of runs where the final answer is still correct (7,000,000).
- Detected is the share of runs the behavior-based detector flagged as abnormal.

| condition | tokens | AF (tokens) | tool calls | AF (calls) | stealth | detected |
|---|---|---|---|---|---|---|
| benign | 3296 | 1.0x | 5.0 | 1.0x | 100% | 0% |
| conflict | 3937 | 1.2x | 5.0 | 1.0x | 0% | 0% |
| fanout | 23935 | 7.3x | 19.0 | 3.8x | 100% | 100% |
| pagination | 12658 | 3.8x | 13.0 | 2.6x | 100% | 100% |
| prompt_injection | 3500 | 1.1x | 5.0 | 1.0x | 100% | 0% |

- The strongest attack is fanout: 7.3 times the tokens and 3.8 times the tool calls,
  with the answer still correct in every trial. Pagination reaches 3.8 times.
- In both, the token cost grows faster than the tool-call count (7.3 versus 3.8 for
  fanout, 3.8 versus 2.6 for pagination).
- That gap is the transcript effect in action: because the whole history is re-sent
  every step, each added call also enlarges every later prompt.

## What did not work

- prompt_injection barely moved the cost (1.1x). The 3B model mostly ignored the
  injected instructions, so the extra work never happened, and a simple keyword
  filter would strip such text anyway. This is why I put the attack into the shape of
  the data instead of into instructions.
- conflict failed on both counts: it barely amplified (1.2x) and it broke the answer
  (0% stealth). Instead of reconciling the disagreeing sources, the model just picked
  figures, often the wrong ones. So it did little extra work and also gave a wrong
  total, which disqualifies it as a quiet attack.
- Obvious sabotage, like telling the agent to ignore the task or loop forever, breaks
  or empties the answer, so it fails the stealth test and is trivial to spot. A cap
  on the number of steps also bounds it.
- pagination and fanout are the reliable levers, because the figure is genuinely
  unavailable without the extra fetches. The agent has no shortcut, so the
  amplification does not depend on the model choosing to obey anything.

## Detection and mitigation

- A content filter is no help here, because a structural attack carries no malicious
  text to match on. So the defense watches behavior instead.
- The detector first learns the normal token cost from benign runs, then flags any
  run that spends far above that (the benign average plus a safety margin).
- In the results it flags fanout and pagination in every trial, with no false alarms
  on benign runs, so it catches the attack by its cost rather than its words.
- For prevention rather than detection, a hard limit on steps and tokens per task
  simply caps the damage.
- The general principle is to compare a run against a known-normal reference and
  raise an alert on the gap that should not be there.
- The deeper fix is architectural. The agent trusts tool output as if it were ground
  truth. Separating untrusted data from the agent's control decisions, for example a
  data-and-plan split, would remove the root cause rather than just the symptom.

## Prepared By

Kawshik Kumar Paul  
Senior Software Engineer | Researcher  
Department of Computer Science and Engineering (CSE)  
Bangladesh University of Engineering and Technology (BUET)  
Email: kawshikbuet17@gmail.com  
