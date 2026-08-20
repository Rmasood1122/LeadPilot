"""M8 code refers to the suppression model as `SuppressionList`; the canonical
class (M2) is `SuppressionEntry` mapped to table `suppression_list`.
Alias — same class, same table."""
from app.db.models import SuppressionEntry as SuppressionList  # noqa: F401
