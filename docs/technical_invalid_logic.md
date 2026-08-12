# 技术无效处理逻辑全图

## 状态流转

```
标注员选择"技术无效" → assignment.status = "issue_reported"
管理员确认废弃 → FinalResult.method = "dropped", final_score = "X"（不参与任何统计）
```

## 完整 Case 矩阵

### Case 1: 仅 A 报无效，B 正常提交

| A | B | 处理 |
|---|---|------|
| issue_reported | submitted | → Third 看全部检查点 → 以 Third 的标注为准（A 的标注视为无效不计入） |

如果 Third 也报无效 → 管理员裁决
如果 Third 正常标注 → 直接定案（method="single"，Third 的答案就是最终答案）

### Case 2: A/B 都报无效

| A | B | 处理 |
|---|---|------|
| issue_reported | issue_reported | → Third 看全部检查点 |

Third 正常标注 → 直接定案（method="single"）
Third 也报无效 → 管理员裁决

### Case 3: A/B 正常但不一致

| A | B | 处理 |
|---|---|------|
| submitted(C) | submitted(N) | → 标准仲裁流程（只看不一致的检查点） |

### Case 4: A/B 一致

| A | B | 处理 |
|---|---|------|
| submitted(C) | submitted(C) | → consensus 直接定案 |

### Case 5: Third 正常但和 A/B 都不同

→ 标准逻辑：`pending_expert` → 管理员裁决

### Case 6: 管理员裁决

管理员看到任务后有两个选择：
- **正常标注** → `FinalResult.method = "expert"`
- **确认废弃(drop)** → `FinalResult.method = "dropped", score = "X"`（整题废弃）

### Case 7: Drop 后的统计

`dropped` 的 FinalResult **不参与任何统计**：
- `scorer.py` 只统计 `final_score IN ("C", "R", "N")`
- `scores/quality` 不计入 dropped
- `scores/fail-codes` 不计入 dropped
- 导出 Excel 中 dropped 的行标注 method="dropped"

## 关于 issue_reported 的已填标注

如果标注员已经填了一些检查点的分数，然后选"技术无效"：
- assignment.status 变为 "issue_reported"
- **已填的标注数据保留在 annotations 表中**（不删除）
- **但不参与比对和定案**（因为该 assignment 不被视为 "submitted"）
- 只有 `status == "submitted"` 的标注才会被 `compare_and_adjudicate` 使用

## 对第三人/管理员展示检查点的逻辑

| 场景 | Third 看到 | 管理员看到 |
|------|-----------|-----------|
| A/B 都报无效 | 全部检查点（needs_annotation=true for all） | 同 Third |
| A 报无效 + B submitted | 全部检查点（B 的标注可参考但不强制跟随） | 全部 |
| A/B submitted 有分歧 | 只看分歧检查点 | 只看 pending_expert |
| Third 也报无效 | - | 全部检查点（管理员可选 drop 或正常标注） |

## Edge Cases

1. **A 报无效后 B 还没提交** → Third 不激活，等 B 也完成
2. **A/B 一个报无效一个正常，没有分歧** → Third 不需要（直接用正常那方的答案？）
   - 不对，应该还是让 Third 确认，因为唯一一份正常标注没有交叉验证
3. **管理员 drop 后想恢复** → 重置该视频（删除 dropped FinalResults + 重新分配）
4. **只有单人模式（无 B 无 Third）时报无效** → 直接推管理员
5. **三人都正常提交但结果全部一样** → consensus 直接定案，Third 不激活
