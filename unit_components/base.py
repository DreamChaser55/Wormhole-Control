from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from entities import Unit
    from game import Game

class UnitComponent:
    """Base class for all components that make up a Unit."""
    DISPLAY_NAME: str = "Component"
    SIDEBAR_ORDER: int = 100

    def __init__(self, unit: 'Unit', hull_cost: int = 0):
        self.unit: 'Unit' = unit
        self.hull_cost: int = hull_cost
        self.max_hit_points: int = max(10, hull_cost * 10)
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
        to render in the sidebar when this component is selected.
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
