# AFC Agent Project Brief

当前 AFC Agent 采用八节点 LangGraph 流程：

1. prepare_context
2. understand_query
3. plan_tools
4. execute_tools
5. merge_evidence
6. evaluate_evidence
7. generate_answer
8. update_memory

语义路由只使用两个字段：

```json
{
  "route": "business_device",
  "business_goal": "device_history"
}
```

`route` 决定处理方式，`business_goal` 决定业务目标。工具规划直接读取这两个字段，不保留旧分类映射。

当前业务能力保持为：数据概览、高风险设备排行、单设备风险预测、历史查询、维修建议、故障类型预测、完整诊断、维修手册检索、多轮追问与缺参追问。
