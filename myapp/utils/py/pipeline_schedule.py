# -*- coding: utf-8 -*-
"""Pipeline 调度增强纯逻辑（企业版 #8/#9）。

自包含模块：仅标准库，禁止 import myapp.*（tests/conftest.py stub 机制前提）。
- priority_spec_patch: 任务流优先级 -> argo workflow spec 增量（双注入）
- expired_run_ids_to_delete: 定时调度过期 RunHistory 记录清理决策
"""

# 档位 -> argo workflow spec.priority 数值（controller 提交排序权重）
PIPELINE_PRIORITY_VALUE = {'high': 200, 'mid': 100, 'low': 0}

# RunHistory 可安全删除的终态（非终态 comed/created 等参与调度链路，永不删）
TERMINAL_RUN_STATUSES = ('Deleted', 'Succeeded', 'Failed')


def priority_spec_patch(pipeline_priority, priority_class_map):
    """计算 workflow spec 的优先级增量。

    双闸门：档位需同时命中 PIPELINE_PRIORITY_VALUE 与 conf 映射表
    priority_class_map（缺省 {} = 功能关闭），才返回注入 patch；
    否则返回 {}，调用方 update 后 spec 与未启用时逐字段一致。
    """
    if not pipeline_priority:
        return {}
    class_name = (priority_class_map or {}).get(pipeline_priority, '')
    value = PIPELINE_PRIORITY_VALUE.get(pipeline_priority)
    if not class_name or value is None:
        return {}
    return {
        'priority': value,
        'templateDefaults': {'priorityClassName': class_name},
    }


def expired_run_ids_to_delete(records, limit, terminal_states=TERMINAL_RUN_STATUSES):
    """返回可删除的过期 RunHistory 记录 id。

    records: [{'id','execution_date','status'}]，execution_date 为
    '%Y-%m-%d %H:%M:%S' 字符串（字典序即时间序）。
    按 execution_date 降序保留最新 limit 条，更早且状态为终态的删除。
    limit<=0 表示不限制，返回 []。
    """
    if not limit or limit <= 0:
        return []
    ordered = sorted(records, key=lambda r: r.get('execution_date') or '', reverse=True)
    return [
        r['id'] for r in ordered[limit:]
        if r.get('status') in terminal_states
    ]
