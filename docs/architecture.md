# AFC Agent Architecture

## Semantic Routing

The Agent uses `route` and `business_goal` as the only semantic routing
standard.

Routes:

- `direct_chat`
- `capability_query`
- `business_global`
- `business_device`
- `needs_clarification`
- `unsupported`

Business goals:

- `data_overview`
- `high_risk_ranking`
- `device_risk`
- `device_history`
- `device_advice`
- `fault_type_prediction`
- `full_diagnosis`
- `manual_search`

## Workflow

The graph keeps the current eight-node process:

`prepare_context -> understand_query -> plan_tools -> execute_tools -> merge_evidence -> evaluate_evidence -> generate_answer -> update_memory`

Cross-turn memory stores `last_assetnum`, `last_route`,
`last_business_goal`, `last_time_window`, message history, tool summaries and
evidence summaries through the checkpointer.

## API Shape

Agent responses expose `route` and `business_goal` directly, alongside
diagnostic metadata such as selected tools, tool trace, evidence packet and
answer mode.
