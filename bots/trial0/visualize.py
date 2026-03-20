from cambc import Controller, Position
from sense import Sense

def visualize_map_minimal(rc: Controller, sense: Sense) -> None:
    """Draw only walls, ore, and buildings (skip empty/unknown)."""
    for y in range(sense.height):
        for x in range(sense.width):
            pos = Position(x, y)
            val = sense.get_entity_id(pos)
            
            if sense.is_enemy_building(pos):
                rc.draw_indicator_dot(pos, 255, 0, 0)  # Enemy building - red
                continue
            if val == 1:
                rc.draw_indicator_dot(pos, 50, 50, 50)  # Wall - dark gray
            elif val == 2:
                rc.draw_indicator_dot(pos, 255, 215, 0)  # Titanium ore - gold
            elif val == 3:
                rc.draw_indicator_dot(pos, 200, 100, 255)  # Axionite ore - purple
            elif val is not None and val > 3:
                rc.draw_indicator_dot(pos, 0, 150, 255)  # Friendly building - blue

def visualize_walls(rc: Controller, sense: Sense) -> None:
    """Draw only known walls."""
    for y in range(sense.height):
        for x in range(sense.width):
            pos = Position(x, y)
            if sense.is_wall(pos):
                rc.draw_indicator_dot(pos, 50, 50, 50)  # Dark gray

def visualize_ore(rc: Controller, sense: Sense) -> None:
    """Draw only known ore."""
    for y in range(sense.height):
        for x in range(sense.width):
            pos = Position(x, y)
            if sense.is_ore_titanium(pos):
                rc.draw_indicator_dot(pos, 255, 215, 0)  # Gold
            elif sense.is_ore_axionite(pos):
                rc.draw_indicator_dot(pos, 200, 100, 255)  # Purple

def visualize_buildings(rc: Controller, sense: Sense) -> None:
    """Draw only known buildings."""
    for y in range(sense.height):
        for x in range(sense.width):
            pos = Position(x, y)
            if sense.is_friendly_building(pos):
                rc.draw_indicator_dot(pos, 0, 150, 255)  # Friendly - blue
            elif sense.is_enemy_building(pos):
                rc.draw_indicator_dot(pos, 255, 0, 0)  # Enemy - red
