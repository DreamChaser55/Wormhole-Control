from typing import Dict, Type
from ..enums import AbilityType
from .base import AbilityDefinition, AbilityInstance
from .adaptive_forcefield import AdaptiveForcefieldAbility
from .cluster_warhead import ClusterWarheadAbility
from .designate_target import DesignateTargetAbility
from .ion_bolt import IonBoltAbility
from .missile_batteries import MissileBatteriesAbility
from .repair_cloud import RepairCloudAbility
from .capture_unit import CaptureUnitAbility

ABILITY_CLASSES: Dict[AbilityType, Type[AbilityInstance]] = {
    AbilityType.ADAPTIVE_FORCEFIELD: AdaptiveForcefieldAbility,
    AbilityType.CLUSTER_WARHEAD: ClusterWarheadAbility,
    AbilityType.DESIGNATE_TARGET: DesignateTargetAbility,
    AbilityType.ION_BOLT: IonBoltAbility,
    AbilityType.MISSILE_BATTERIES: MissileBatteriesAbility,
    AbilityType.REPAIR_CLOUD: RepairCloudAbility,
    AbilityType.CAPTURE_UNIT: CaptureUnitAbility,
}

ABILITY_DEFINITIONS: Dict[AbilityType, AbilityDefinition] = {
    atype: cls.DEFINITION for atype, cls in ABILITY_CLASSES.items()
}
