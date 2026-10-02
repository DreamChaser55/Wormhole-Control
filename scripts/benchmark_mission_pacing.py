"""Offline Normal-opening travel and starter egress estimates."""
from pathlib import Path
import json
import statistics
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from antimatter_logistics import estimate_approach
from campaign_graph import iter_units
from constants import DEFAULT_STANDOFF_DISTANCE
from game_settings import GameSettings, PlayerConfig
from game_setup import prepare_new_campaign
from geometry import Circle, Position, get_closest_point_on_circle_edge, hex_distance
from player_controller import PlayerController


def measure(seeds=(9302026, 42, 17, 123, 2026)):
    samples = []
    egress = []
    for seed in seeds:
        settings = GameSettings(seed=seed, num_systems=2, system_radius_min=3, system_radius_max=3,
            spawn_profile='normal', player_configs=[PlayerConfig('One', (0, 200, 0), PlayerController.HUMAN, 1),
                                                  PlayerConfig('Two', (200, 0, 0), PlayerController.HUMAN, 2)])
        game = prepare_new_campaign(settings).state
        for player in game.players:
            world = game.galaxy.get_celestial_body_by_id(player.homeworld_id)
            zone = Circle(world.position, world.inhibition_field_radius + 1)
            for actor, _ in iter_units(game.galaxy):
                if actor.owner != player or not actor.engines_component or actor.colony_component:
                    continue
                old_offset = Position(-250, -750) if actor.constructor_component else Position(0, -900)
                estimates = {}
                for label, start in (('previous', world.position + old_offset), ('current', actor.position)):
                    target = SimpleNamespace(in_system=actor.in_system, in_hex=actor.in_hex,
                        position=get_closest_point_on_circle_edge(start, zone))
                    estimate = estimate_approach(actor, game.galaxy, target,
                        (actor.in_system, actor.in_hex, start), approach_range=5, known_only=True)
                    estimates[label + '_owner_turns'] = estimate.turns if estimate else None
                egress.append({'seed': seed, 'player': player.name, 'ship': actor.name, **estimates})
            unit = next(actor for actor, _ in iter_units(game.galaxy) if actor.owner == player and actor.colony_component)
            targets = [body for sector in game.galaxy.systems[unit.in_system].hexes.values()
                       for body in sector.celestial_bodies if getattr(body, 'is_colonizable', False)
                       and body.owner is None and hex_distance(unit.in_hex, body.in_hex) == 1]
            for target in sorted(targets, key=lambda body: body.id):
                reach = target.collision_radius + DEFAULT_STANDOFF_DISTANCE
                estimate = estimate_approach(unit, game.galaxy, target, approach_range=reach, known_only=True)
                samples.append({'seed': seed, 'player': player.name, 'ship': unit.name,
                    'speed': unit.engines_component.effective_speed, 'target': target.name,
                    'owner_turns': estimate.turns if estimate else None,
                    'estimated_antimatter': round(estimate.fuel, 2) if estimate else None})
    feasible = [sample['owner_turns'] for sample in samples if sample['owner_turns'] is not None]
    egress_medians = {label: statistics.median(sample[label + '_owner_turns'] for sample in egress
                                             if sample[label + '_owner_turns'] is not None)
                      for label in ('previous', 'current')}
    return {'profile': 'Normal', 'systems': 2, 'radius': 3,
            'note': 'Remaining travel only; assumes sufficient fuel and unchanged terrain. Loading, action time and queued work are excluded.',
            'median_owner_turns': statistics.median(feasible) if feasible else None,
            'maximum_owner_turns': max(feasible) if feasible else None, 'samples': samples,
            'starter_egress_median_owner_turns': egress_medians, 'starter_egress_samples': egress}


if __name__ == '__main__':
    print(json.dumps(measure(), indent=2))
