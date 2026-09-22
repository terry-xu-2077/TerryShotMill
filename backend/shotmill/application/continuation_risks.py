MISSING_PREVIOUS_VIDEO = (
    "上一任务尚无视频结果，本次将不使用尾帧承接直接生成，人物、构图和动作可能与上一任务不连续。"
)


def continuation_risks(uow, task):
    jobs = uow.jobs.list_by_task(task.id)
    active = next((job for job in jobs if job.status.value in {"queued", "running"}), None)
    if active and active.context_snapshot.get("dependency"):
        if active.error_code == "CONTEXT_DEPENDENCY_UNAVAILABLE":
            return [active.error_message]
        return []
    if task.generation_params.get("contextMode", "尾帧承接") != "尾帧承接":
        return []
    previous = next(
        (
            item
            for item in reversed(uow.tasks.list_by_project(task.project_id))
            if item.display_order < task.display_order
        ),
        None,
    )
    if previous and not previous.primary_result_id:
        return [MISSING_PREVIOUS_VIDEO]
    return []


def continuation_status(uow, task):
    active = next(
        (job for job in uow.jobs.list_by_task(task.id) if job.status.value == "queued"), None
    )
    if active and active.context_snapshot.get("dependency") and active.execution_context is None:
        if active.error_code == "CONTEXT_DEPENDENCY_UNAVAILABLE":
            return "承接异常 · 待确认"
        if uow.runtime_controls.get(active.id).paused:
            return "已挂起"
        return "等待上一任务结果"
    return None
