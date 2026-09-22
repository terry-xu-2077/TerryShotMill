from shotmill.domain.entities import utcnow
from shotmill.domain.enums import JobStatus, TaskState
from shotmill.errors import ConflictError, NotFoundError


class RuntimeControlService:
    def __init__(self, generation, batches):
        self.generation = generation
        self.batches = batches
        self.uow_factory = generation.uow_factory

    async def act(self, project_id, kind, job_id, action):
        resume = False
        batch_id = None
        with self.uow_factory() as uow:
            repository = uow.jobs if kind == "video" else uow.prompt_jobs
            job = repository.get(job_id)
            if job is None or job.project_id != project_id:
                raise NotFoundError("JOB_NOT_FOUND", "任务记录不存在")
            if job.status == JobStatus.RUNNING:
                raise ConflictError("JOB_RUNNING", "正在执行的任务不能排序、挂起或移除")
            control = uow.runtime_controls.get(job_id)
            if action != "remove" and (job.status != JobStatus.QUEUED or control.hidden):
                raise ConflictError("JOB_NOT_QUEUED", "仅待执行任务可以排序、挂起或恢复")
            if action in {"up", "down"}:
                jobs = repository.list_active()
                queued = [item for item in jobs if item.status == JobStatus.QUEUED]
                controls = {item.id: uow.runtime_controls.get(item.id) for item in queued}
                queued.sort(
                    key=lambda item: (
                        controls[item.id].position
                        if controls[item.id].position is not None
                        else float("inf"),
                    )
                )
                # Move within the project; persist priority in the actual global queue.
                indexes = [i for i, item in enumerate(queued) if item.project_id == project_id]
                local = next(i for i, index in enumerate(indexes) if queued[index].id == job_id)
                other = local + (-1 if action == "up" else 1)
                if 0 <= other < len(indexes):
                    a, b = indexes[local], indexes[other]
                    queued[a], queued[b] = queued[b], queued[a]
                for index, item in enumerate(queued):
                    value = controls[item.id]
                    value.position = index
                    uow.runtime_controls.save(value)
            elif action in {"pause", "resume"}:
                resume = action == "resume" and control.paused
                control.paused = action == "pause"
                uow.runtime_controls.save(control)
            elif action == "remove":
                control.hidden = True
                control.paused = False
                if job.status == JobStatus.QUEUED:
                    job.status = JobStatus.CANCELLED
                    if kind == "video":
                        job.completed_at = utcnow()
                        uow.jobs.update_runtime(job)
                    else:
                        job.finished_at = utcnow()
                        uow.prompt_jobs.update(job)
                        batch_id = job.batch_id
                    task = uow.tasks.get(job.task_id)
                    video_ids = uow.jobs.active_task_ids_by_project(project_id)
                    prompt_ids = uow.prompt_jobs.active_task_ids_by_project(project_id)
                    if task and task.id not in video_ids and task.id not in prompt_ids:
                        task.state = (
                            TaskState.COMPLETED
                            if task.primary_result_id
                            else TaskState.PROMPT_READY
                            if task.final_prompt.strip()
                            else TaskState.DRAFT
                        )
                        task.progress = 100.0 if task.primary_result_id else None
                        task.updated_at = utcnow()
                        uow.tasks.update(task)
                uow.runtime_controls.save(control)
        if kind == "video" and action == "remove":
            await self.generation.wake_dependents(job_id)
        if batch_id:
            self.batches.refresh_prompt_batch(batch_id)
        if resume:
            queue = self.generation.queue if kind == "video" else self.batches.prompt_queue
            await queue.enqueue(job_id)
        await self.generation.events.publish(project_id, "project.runtime_changed")
        await self.generation.events.publish(project_id, "project.summary_changed")
