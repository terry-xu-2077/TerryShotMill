import pytest
from shotmill.domain.entities import Project, Scene, Task, TaskPlacement
from shotmill.persistence.database import create_database_engine
from shotmill.persistence.migrations import upgrade_database
from shotmill.persistence.repositories.uow import SqlAlchemyUnitOfWork
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def story_uow(tmp_path):
    url = f"sqlite+pysqlite:///{(tmp_path / 'story.db').as_posix()}"
    upgrade_database(url)
    engine = create_database_engine(url)
    factory = sessionmaker(engine)
    try:
        yield lambda: SqlAlchemyUnitOfWork(factory)
    finally:
        engine.dispose()


def test_scene_placement_roundtrip_preserves_hidden_structure_and_task_order(story_uow):
    with story_uow() as uow:
        uow.projects.add(Project(id="p", title="Project"))
        uow.story_structure.add_scene(Scene("s2", "p", 2, "Later", "Summary", 20))
        uow.story_structure.add_scene(Scene("s1", "p", 1, "First", "", 10))
        uow.tasks.add(Task(id="t", project_id="p", display_order=1, title="Task"))
        uow.story_structure.place_task("p", TaskPlacement("t", "s2", 35))
    with story_uow() as uow:
        assert uow.story_structure.list_scenes("p") == [
            Scene("s1", "p", 1, "First", "", 10),
            Scene("s2", "p", 2, "Later", "Summary", 20),
        ]
        assert uow.story_structure.list_placements("p") == [TaskPlacement("t", "s2", 35)]
        assert uow.tasks.get("t").display_order == 1
        assert uow.story_structure.list_scenes("other") == []
        assert uow.story_structure.list_placements("other") == []


@pytest.mark.parametrize("project_id,task_id,scene_id", [
    ("p", "t", "s-other"), ("other", "t", "s-other"),
    ("p", "missing", "s"), ("p", "t", "missing"),
])
def test_placement_rejects_foreign_or_missing_owners(story_uow, project_id, task_id, scene_id):
    with story_uow() as uow:
        uow.projects.add(Project(id="p", title="Project"))
        uow.projects.add(Project(id="other", title="Other"))
        uow.story_structure.add_scene(Scene("s", "p"))
        uow.story_structure.add_scene(Scene("s-other", "other"))
        uow.tasks.add(Task(id="t", project_id="p", display_order=1, title="Task"))
    with pytest.raises(ValueError, match="same project"), story_uow() as uow:
        uow.story_structure.place_task(project_id, TaskPlacement(task_id, scene_id, 99))
    with story_uow() as uow:
        assert uow.story_structure.list_placements("p") == [TaskPlacement("t", "s", 1)]


def test_scene_and_placement_changes_rollback_together(story_uow):
    with story_uow() as uow:
        uow.projects.add(Project(id="p", title="Project"))
        uow.story_structure.add_scene(Scene("s", "p"))
        uow.tasks.add(Task(id="t", project_id="p", display_order=1, title="Task"))
    with pytest.raises(RuntimeError), story_uow() as uow:
        uow.story_structure.add_scene(Scene("new", "p", order_key=2))
        uow.story_structure.place_task("p", TaskPlacement("t", "new", 20))
        raise RuntimeError("import aborted")
    with story_uow() as uow:
        assert uow.story_structure.list_scenes("p") == [Scene("s", "p")]
        assert uow.story_structure.list_placements("p") == [TaskPlacement("t", "s", 1)]
