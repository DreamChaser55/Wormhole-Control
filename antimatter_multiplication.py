"""Pure previews and authoritative execution of the antimatter pulse."""

from antimatter_logistics import endpoint_ready
from domain.players import are_allies
from geometry import distance


def preview(unit, galaxy, amount_for=None, ready_for=None, excluded=()):
    from tactical_balance import SPECS

    spec = SPECS["multiply_antimatter"]
    now = getattr(unit.game, "turn_number", 1)
    amount_for = amount_for or (
        lambda target: target.antimatter_component.current_amount
    )
    ready_for = ready_for or (lambda target: target.multiply_receive_ready_round)
    if amount_for(unit) < spec.cost:
        return []
    sector = galaxy.systems[unit.in_system].hexes[unit.in_hex]
    gains = []
    for target in sector.units:
        if (
            target.id in excluded
            or not endpoint_ready(target, galaxy)
            or not are_allies(unit.owner, target.owner)
            or distance(unit.position, target.position) > spec.range
            or ready_for(target) > now
        ):
            continue
        before = amount_for(target) - (spec.cost if target is unit else 0)
        added = min(
            max(0.0, before),
            max(0.0, target.antimatter_component.max_capacity - before),
        )
        if added > 0:
            gains.append((target, added))
    return gains


def activate(unit, galaxy):
    from tactical_balance import SPECS

    spec = SPECS["multiply_antimatter"]
    gains = preview(unit, galaxy)
    if sum(amount for _, amount in gains) <= spec.cost:
        return False
    if not unit.antimatter_component.consume(spec.cost):
        return False
    ready = unit.game.turn_number + spec.cooldown
    for target, amount in gains:
        target.antimatter_component.add(amount)
        target.multiply_receive_ready_round = ready
    unit.multiply_cast_ready_round = ready
    return True
