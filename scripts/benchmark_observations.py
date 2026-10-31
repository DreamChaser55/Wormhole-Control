"""Compare fixed Normal/Testing observation character sizes without API calls."""
import json
from generate_reference import isolated_environment


def main():
    with isolated_environment():
        from game_settings import GameSettings, PlayerConfig
        from player_controller import PlayerController
        from game_setup import prepare_new_campaign
        from game_ai.observation import build_observation
        from game_ai.adapters.base import PlanningRequest
        from game_ai.prompt_context import planning_context
        from game_ai.memory import AgentMemory
        for profile in ('normal', 'testing'):
            settings = GameSettings(seed=20260930, spawn_profile=profile, num_systems=2,
                system_radius_min=3, system_radius_max=3,
                player_configs=[PlayerConfig('Codex', (30, 120, 255), PlayerController.CODEX, 1),
                                PlayerConfig('Rival', (220, 40, 40), PlayerController.HUMAN, 2)])
            game = prepare_new_campaign(settings).state
            player = game.players[0]
            observation = build_observation(game, player)
            request = PlanningRequest('benchmark', 'benchmark', player.name, 1,
                                      observation, AgentMemory().to_dict())
            _, metrics = planning_context(request)
            _, baseline = planning_context(request, compact=False)
            metrics['unfactored_content_input_chars'] = baseline['content_input_chars']
            metrics['content_reduction_fraction'] = round(1 - metrics['content_input_chars'] / baseline['content_input_chars'], 4)
            print(json.dumps({'profile': profile, 'seed': settings.seed, 'systems': 2,
                              'radius': 3, 'units_in_observation': len(observation['units']), **metrics}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
