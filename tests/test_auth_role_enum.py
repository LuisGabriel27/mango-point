import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.models import UserAccount, UserRoleEnum


def test_user_role_enum_uses_database_values_not_member_names():
    role_type = UserAccount.__table__.c.role.type

    assert role_type.enums == ["admin", "analyst", "operator"]
    assert role_type._db_value_for_elem(UserRoleEnum.ADMIN) == "admin"
    assert role_type._object_value_for_elem("admin") is UserRoleEnum.ADMIN
