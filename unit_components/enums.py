from enum import Enum, auto

class HyperdriveType(Enum):
    BASIC = "basic"  # Inter-sector travel only
    ADVANCED = "advanced" # Wormhole travel capable

class JumpStatus(Enum):
    CHARGING = "charging"
    READY = "ready"
    JUMPING = "jumping"
    ERROR = "error"

class UnitStance(Enum):
    DO_NOTHING = "do_nothing"
    ATTACK_WEAPON_RANGE = "attack_weapon_range"
    ATTACK_SAME_SECTOR = "attack_same_sector"
    ATTACK_INTRA_SYSTEM_JUMP_RANGE = "attack_intra_system_jump_range"
    ATTACK_SAME_SYSTEM = "attack_same_system"

    @property
    def display_name(self) -> str:
        if self == UnitStance.DO_NOTHING:
            return "Do Nothing"
        elif self == UnitStance.ATTACK_WEAPON_RANGE:
            return "Attack in Weapon Range"
        elif self == UnitStance.ATTACK_SAME_SECTOR:
            return "Attack in Same Sector"
        elif self == UnitStance.ATTACK_INTRA_SYSTEM_JUMP_RANGE:
            return "Attack in Jump Range"
        elif self == UnitStance.ATTACK_SAME_SYSTEM:
            return "Attack in Same System"
        return self.name.replace("_", " ").title()

class TurretType(Enum):
    MASS_DRIVER = "mass_driver"
    BEAM = "beam"
    MISSILE = "missile"

class TurretVariant(Enum):
    STANDARD = "standard"
    ANTI_STRIKECRAFT = "anti_strikecraft"
    LONG_RANGE = "long_range"

class WingType(Enum):
    FIGHTER = "fighter"
    BOMBER = "bomber"

class AbilityType(Enum):
    ADAPTIVE_FORCEFIELD = "adaptive_forcefield"
    CLUSTER_WARHEAD = "cluster_warhead"
    DESIGNATE_TARGET = "designate_target"
    ION_BOLT = "ion_bolt"
    MISSILE_BATTERIES = "missile_batteries"
    REPAIR_CLOUD = "repair_cloud"
    CAPTURE_UNIT = "capture_unit"
