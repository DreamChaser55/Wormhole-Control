"""Registry adapters for tactical abilities; rules live in tactical_abilities."""
from .base import AbilityDefinition, AbilityInstance
from ..enums import AbilityType
from tactical_abilities import SPECS, GUARDIAN_FRACTION, GUARDIAN_CAP, GUARDIAN_RETAINED


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


def _ability_class(kind, spec):
    definition = AbilityDefinition(AbilityType(kind), spec.name, spec.description,
        spec.cooldown, spec.duration, spec.range, spec.target_kind == 'unit',
        spec.target_kind in ('position', 'celestial_position'), spec.cost, list(spec.equipment))
    return type(''.join(part.title() for part in kind.split('_')) + 'Ability', (TacticalAbility,), {'DEFINITION': definition})


TACTICAL_CLASSES = {AbilityType(kind): _ability_class(kind, spec) for kind, spec in SPECS.items()}
