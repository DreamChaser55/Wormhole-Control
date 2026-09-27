"""Registry adapters for tactical abilities; rules live in tactical_abilities."""
from .base import AbilityDefinition, AbilityInstance
from ..enums import AbilityType
from tactical_abilities import SPECS, GUARDIAN_FRACTION, GUARDIAN_CAP, GUARDIAN_RETAINED, TRACTOR_COST


class TacticalAbility(AbilityInstance):
    STATE_FIELDS = AbilityInstance.STATE_FIELDS + ('ready_round', 'expires_round', 'last_pull_round', 'source_owner_id', 'target_body_id', 'redirect_fraction', 'redirect_cap', 'redirect_retained')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ready_round = None
        self.expires_round = None
        self.last_pull_round = None
        self.source_owner_id = None
        self.target_body_id = None
        self.redirect_fraction = GUARDIAN_FRACTION
        self.redirect_cap = GUARDIAN_CAP
        self.redirect_retained = GUARDIAN_RETAINED

    def validate_state(self):
        from state_codec import number
        for field in self.STATE_FIELDS[6:11]:
            value = getattr(self, field)
            if value is not None:
                number(value, 'tactical.' + field, 0, integer=True)
        number(self.redirect_fraction, 'tactical.redirect_fraction', 0)
        number(self.redirect_retained, 'tactical.redirect_retained', 0)
        if self.redirect_fraction > 1 or self.redirect_retained > 1:
            raise ValueError('Guardian fractions must not exceed one')
        number(self.redirect_cap, 'tactical.redirect_cap', 0, integer=True)


class StrikecraftAbility(TacticalAbility):
    STATE_FIELDS = TacticalAbility.STATE_FIELDS + ('participant_ids',)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.participant_ids = []

    def validate_state(self):
        super().validate_state()
        from state_codec import number
        if not isinstance(self.participant_ids, list) or len(set(self.participant_ids)) != len(self.participant_ids):
            raise ValueError('Invalid strikecraft participants')
        for uid in self.participant_ids:
            number(uid, 'strikecraft.participant_id', 0, integer=True)


class TitanAbility(TacticalAbility):
    STATE_FIELDS = TacticalAbility.STATE_FIELDS + ('system_name', 'hex_coord', 'origin_position', 'charge_round', 'order_id')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.system_name = None
        self.hex_coord = None
        self.origin_position = None
        self.charge_round = None
        self.order_id = None

    def validate_state(self):
        super().validate_state()
        from state_codec import number
        from geometry import Position
        for field in ('charge_round',):
            if getattr(self, field) is not None:
                number(getattr(self, field), 'titan.' + field, 0, integer=True)
        if self.order_id is not None and not isinstance(self.order_id, str):
            raise ValueError("Invalid Titan order ID")
        if self.system_name is not None and (not isinstance(self.system_name, str) or not self.system_name):
            raise ValueError('Invalid Titan system')
        if self.hex_coord is not None and (not isinstance(self.hex_coord, tuple) or len(self.hex_coord) != 2 or any(type(v) is not int for v in self.hex_coord)):
            raise ValueError('Invalid Titan sector')
        if self.origin_position is not None and not isinstance(self.origin_position, Position):
            raise ValueError('Invalid Titan origin')
        if self.is_active and (self.system_name is None or self.hex_coord is None or self.source_owner_id is None):
            raise ValueError('Missing active Titan location or owner')
        if self.is_active:
            if self.ready_round is None or self.expires_round is None:
                raise ValueError('Missing active Titan deadlines')
            if self.definition.ability_type == AbilityType.SIEGE_LANCE and (
                    self.charge_round is None or self.origin_position is None
                    or not self.order_id or self.target_unit_id is None):
                raise ValueError('Missing Siege Lance charge state')


def _ability_class(kind, spec):
    definition = AbilityDefinition(AbilityType(kind), spec.name, spec.description,
        spec.cooldown, spec.duration, spec.range, spec.target_kind == 'unit',
        spec.target_kind in ('position', 'celestial_position'), spec.cost, list(spec.equipment),
        ongoing_antimatter=TRACTOR_COST if kind == 'tractor_tether' else 0)
    from tactical_balance import STRIKECRAFT_ABILITIES
    from titan_balance import TITAN_ABILITIES
    base = TitanAbility if kind in TITAN_ABILITIES else StrikecraftAbility if kind in STRIKECRAFT_ABILITIES else TacticalAbility
    return type(''.join(part.title() for part in kind.split('_')) + 'Ability', (base,), {'DEFINITION': definition})


TACTICAL_CLASSES = {AbilityType(kind): _ability_class(kind, spec) for kind, spec in SPECS.items()}
