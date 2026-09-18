"""Continuous harvesting and storage-based antimatter donation."""
from .base import OrderType, OrderTargetField
from .fuel_transport import ContinuousFuelDeliveryOrder, TransferAntimatterOrder

__all__ = ["ContinuousResupplyOrder", "TransferAntimatterOrder"]


class ContinuousResupplyOrder(ContinuousFuelDeliveryOrder):
    """Harvest at a fixed celestial source and supply manual or automatic recipients."""
    HARVESTING = True
    TYPE = OrderType.CONTINUOUS_RESUPPLY
    SOURCE_FIELD = "source_body_id"
    target_fields = (
        OrderTargetField("source_body_id", "celestial", public=True),
        OrderTargetField("target_unit_id", "unit", public=True),
    )
