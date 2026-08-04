from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from entities import Unit
    from game import Game

class UnitComponent:
    """Base class for all components that make up a Unit."""
    DISPLAY_NAME: str = "Component"
    SIDEBAR_ORDER: int = 100

    def __init__(self, unit: 'Unit', hull_cost: float = 0.0):
        self.unit: 'Unit' = unit
        self.hull_cost: float = float(hull_cost)
        self.max_hit_points: int = max(10, int(round(float(hull_cost) * 10)))
        self.current_hit_points: int = self.max_hit_points

    @property
    def is_destroyed(self) -> bool:
        return self.current_hit_points <= 0

    def on_destroyed(self) -> None:
        """Called when the component's hit points reach 0."""
        pass

    def get_sidebar_data(self, game_state: 'Game') -> list[dict]:
        """
        Returns a list of UI element definitions (labels, progress bars, buttons)
        to render in the sidebar when this component is selected in Components panel.
        """
        status = "DESTROYED" if self.is_destroyed else f"HP: {self.current_hit_points}/{self.max_hit_points}"
        return [
            {
                'type': 'label',
                'text': f"{self.DISPLAY_NAME} [{status}]",
                'object_id': '#sidebar_section_header_label',
                'height': 28
            }
        ]

    def get_basic_sidebar_data(self, game_state: 'Game') -> list[dict]:
        """
        Returns a list of concise UI element definitions for the Basic Info panel.
        Can be overridden by subclasses to highlight key component stats.
        """
        if self.is_destroyed:
            return [{
                'type': 'label',
                'text': f"• Destroyed Component: {self.DISPLAY_NAME}",
                'object_id': '#sidebar_hit_points_critical_damage_label',
                'height': 18,
                'indent_level': 1
            }]
        return []

    @staticmethod
    def calc_hull_cost(*args, **kwargs) -> float:
        """Compute the dynamic hull cost of the component from its design parameters."""
        return 0.0


