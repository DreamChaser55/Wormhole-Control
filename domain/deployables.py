"""Persistent tactical objects, deliberately separate from ships."""
from domain.identity import GameObject
from constants import HullSize
from tactical_balance import DEPLOYABLE_HP, CACHE_FUEL, CATALYST_RADIUS


class DeploymentProvenance:
    @property
    def deploying_ship_id(self):
        return self._deploying_ship_id

    @property
    def deploying_player_id(self):
        return self.owner.id


class Deployable(DeploymentProvenance, GameObject):
    hull_size = HullSize.TINY
    max_hit_points = DEPLOYABLE_HP
    damage_amplification = 0.0
    damage_reduction = 0.0
    is_hidden_in_gas_giant = False
    is_disabled = False
    engines_component = None
    hyperdrive_component = None
    inhibitor_component = None
    cloaking_component = None
    weapons_component = None
    commander_component = None
    sensors_component = None
    ability_component = None
    components = {}

    def __init__(self, owner, position, in_hex, in_system, kind, deploying_ship_id, galaxy=None):
        super().__init__(position, in_hex, in_system)
        self.owner = owner
        self.kind = kind
        self._deploying_ship_id = deploying_ship_id
        self.name = 'Ghost Emitter' if kind == 'ghost_fleet' else 'Fuel Cache'
        self.current_hit_points = DEPLOYABLE_HP
        self.fuel = float(CACHE_FUEL) if kind == 'fuel_cache' else 0.0
        self.identified_player_ids = set()
        self.in_galaxy = galaxy

    def get_component(self, component_type):
        return None

    def take_damage(self, amount, damage_type=None, *, is_splash=False):
        if is_splash:
            from environmental_effects import splash_damage
            amount = splash_damage(amount, self)
        if amount > 0:
            self.current_hit_points = max(0, self.current_hit_points - int(amount))
            if self.current_hit_points == 0:
                self.destroy()

    def destroy(self):
        self.current_hit_points = 0
        if self.in_galaxy:
            system = self.in_galaxy.systems.get(self.in_system)
            sector = system.hexes.get(self.in_hex) if system else None
            if sector and self in sector.deployables:
                sector.deployables.remove(self)


class CatalystPatch(DeploymentProvenance, GameObject):
    def __init__(self, owner, position, in_hex, in_system, deploying_ship_id, nebula_id, expires_round):
        super().__init__(position, in_hex, in_system)
        self.owner = owner
        self._deploying_ship_id = deploying_ship_id
        self.nebula_id = nebula_id
        self.expires_round = expires_round
        self.radius = CATALYST_RADIUS
        self.name = 'Nebula Catalyst'
