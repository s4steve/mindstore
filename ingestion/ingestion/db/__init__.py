# Re-export all public functions so that `from . import db as db_module`
# followed by `db_module.create_task(...)` etc. continues to work unchanged.

from ._helpers import check_connection, create_pool  # noqa: F401
from .contacts import (  # noqa: F401
    create_contact,
    delete_contact,
    get_contact,
    list_contacts,
    log_interaction,
    update_contact,
)
from .home import (  # noqa: F401
    complete_home_item,
    create_home_item,
    delete_home_item,
    get_home_item,
    list_home_items,
    update_home_item,
)
from .search import (  # noqa: F401
    cross_table_search,
    get_all_tags,
    get_dashboard,
    get_items_by_tag,
    get_related_tags,
    get_suggested_connections,
)
from .tasks import (  # noqa: F401
    complete_task,
    create_task,
    delete_task,
    get_task,
    list_tasks,
    update_task,
)
from .thoughts import (  # noqa: F401
    delete_thought,
    get_recent,
    get_stats,
    get_thought_full,
    insert_thought,
    semantic_search,
    update_thought,
)
