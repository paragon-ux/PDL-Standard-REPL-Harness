# Condition C ICM Workspace

Layer 0 / Layer 1 routing surface for one Condition C run.

This workspace is a non-normative orchestration substrate. Protocol correctness is
defined only by `contracts/standards/` in the installed runtime. The deterministic
controller selects the next legal stage; the workspace controls context flow by
materializing only that stage's declared inputs, references, and outputs.

Default stage topology:

```text
00_activation
10_prompt
20_prompt_review
30_plan
40_plan_review
50_execution
90_protocol_discussion
```

Numeric prefixes provide stable stage routing and the ordinary workflow order. Dynamic
loops and branches are selected by the controller rather than inferred from folder order.
