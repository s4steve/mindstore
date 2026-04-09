# Re-export all public functions so that `from . import db as db_module`
# followed by `db_module.create_task(...)` etc. continues to work unchanged.

from ._helpers import create_pool, check_connection  # noqa: F401

from .thoughts import (  # noqa: F401
    insert_thought,
    delete_thought,
    update_thought,
    get_recent,
    get_thought_full,
    semantic_search,
    get_stats,
)

from .tasks import (  # noqa: F401
    create_task,
    list_tasks,
    get_task,
    update_task,
    delete_task,
    complete_task,
)

from .contacts import (  # noqa: F401
    create_contact,
    list_contacts,
    get_contact,
    update_contact,
    delete_contact,
    log_interaction,
)

from .home import (  # noqa: F401
    create_home_item,
    list_home_items,
    get_home_item,
    update_home_item,
    delete_home_item,
    complete_home_item,
)

from .search import (  # noqa: F401
    cross_table_search,
    get_all_tags,
    get_items_by_tag,
    get_related_tags,
    get_suggested_connections,
    get_dashboard,
)
