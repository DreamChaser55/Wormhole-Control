"""Indefinite toggle instances; environmental_resistance owns their rules."""
from environmental_resistance import SPECS, description
from .base import AbilityDefinition, AbilityInstance
from ..enums import AbilityType


class ResistanceAbility(AbilityInstance):
    def validate_state(self):
        definition = self.definition
        if (definition.cooldown or definition.duration or definition.range or definition.antimatter_cost
                or definition.requires_target_unit or definition.requires_target_position):
            raise ValueError('Resistance definitions must be free, untimed, self-only toggles')
        if (self.cooldown_remaining or self.duration_remaining or self.target_unit_id is not None
                or self.target_position is not None or self.spawned_unit_ids):
            raise ValueError('Resistance toggles cannot have timers, targets or deployments')


def _ability_class(kind, spec):
    definition = AbilityDefinition(AbilityType(kind), spec.name, description(kind),
        0, 0, 0, False, False, required_components=['has_antimatter_storage'],
        activation_mode='toggle', ongoing_antimatter=spec.upkeep)
    return type(''.join(part.title() for part in kind.split('_')) + 'Ability',
                (ResistanceAbility,), {'DEFINITION': definition})


RESISTANCE_CLASSES = {AbilityType(kind): _ability_class(kind, spec) for kind, spec in SPECS.items()}
