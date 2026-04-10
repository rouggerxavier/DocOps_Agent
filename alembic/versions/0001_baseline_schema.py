"""baseline schema snapshot"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from docops.db import models  # noqa: F401
    from docops.db.database import Base

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    from docops.db import models  # noqa: F401
    from docops.db.database import Base

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
