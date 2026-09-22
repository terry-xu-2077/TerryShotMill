from sqlalchemy import select

from shotmill.domain.runtime_control import RuntimeControl
from shotmill.persistence.models import RuntimeControlModel


class SqlAlchemyRuntimeControlRepository:
    def __init__(self, session):
        self.session = session

    def get(self, job_id):
        row = self.session.get(RuntimeControlModel, job_id)
        return (
            RuntimeControl(row.job_id, row.paused, row.hidden, row.position)
            if row
            else RuntimeControl(job_id)
        )

    def all(self):
        return {
            row.job_id: RuntimeControl(row.job_id, row.paused, row.hidden, row.position)
            for row in self.session.scalars(select(RuntimeControlModel))
        }

    def save(self, value):
        self.session.merge(
            RuntimeControlModel(
                job_id=value.job_id,
                paused=value.paused,
                hidden=value.hidden,
                position=value.position,
            )
        )
        self.session.flush()
