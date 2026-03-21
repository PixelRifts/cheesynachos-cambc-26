from cambc import Controller, Position, EntityType
from sense import Sense

def visualize_map_minimal(rc: Controller, sense: Sense) -> None:
    """Draw only walls, ore, and buildings (skip empty/unknown)."""
    for y in range(sense.height):
        for x in range(sense.width):
            pos = Position(x, y)
            
            if sense.is_enemy_building(pos):
                etype = sense.get_building_type(pos)
                if etype == EntityType.CORE:
                    rc.draw_indicator_dot(pos, 255, 0, 255)  # Enemy core - magenta
                elif etype in (EntityType.GUNNER, EntityType.SENTINEL, EntityType.BREACH):
                    rc.draw_indicator_dot(pos, 255, 100, 0)  # Enemy turret - orange
                else:
                    rc.draw_indicator_dot(pos, 255, 0, 0)  # Enemy building - red
            elif sense.is_wall(pos):
                rc.draw_indicator_dot(pos, 50, 50, 50)  # Wall - dark gray
            elif sense.is_ore_titanium(pos):
                rc.draw_indicator_dot(pos, 255, 215, 0)  # Titanium ore - gold
            elif sense.is_ore_axionite(pos):
                rc.draw_indicator_dot(pos, 200, 100, 255)  # Axionite ore - purple

            elif sense.is_friendly_building(pos):
                etype = sense.get_building_type(pos)
                if etype == EntityType.CORE:
                    rc.draw_indicator_dot(pos, 0, 255, 255)  # Friendly core - cyan
                elif etype in (EntityType.GUNNER, EntityType.SENTINEL, EntityType.BREACH):
                    rc.draw_indicator_dot(pos, 100, 200, 0)  # Friendly turret - lime
                elif etype == EntityType.ROAD:
                    rc.draw_indicator_dot(pos, 255, 255, 255)  # Road - white
                elif etype == EntityType.MARKER:
                    rc.draw_indicator_dot(pos, 255, 255, 0)  # Marker - yellow
                else:
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
    """Draw only known buildings with type-specific colors."""
    for y in range(sense.height):
        for x in range(sense.width):
            pos = Position(x, y)
            
            if sense.is_friendly_building(pos):
                etype = sense.get_building_type(pos)
                if etype == EntityType.CORE:
                    rc.draw_indicator_dot(pos, 0, 255, 255)  # Friendly core - cyan
                elif etype in (EntityType.GUNNER, EntityType.SENTINEL, EntityType.BREACH):
                    rc.draw_indicator_dot(pos, 100, 200, 0)  # Friendly turret - lime
                elif etype == EntityType.ROAD:
                    rc.draw_indicator_dot(pos, 255, 255, 255)  # Road - white
                elif etype == EntityType.MARKER:
                    rc.draw_indicator_dot(pos, 255, 255, 0)  # Marker - yellow
                elif etype in (EntityType.CONVEYOR, EntityType.SPLITTER, EntityType.ARMOURED_CONVEYOR):
                    rc.draw_indicator_dot(pos, 0, 100, 150)  # Friendly logistics - dark blue
                elif etype in (EntityType.HARVESTER, EntityType.FOUNDRY):
                    rc.draw_indicator_dot(pos, 255, 200, 0)  # Friendly economy - yellow-orange
                else:
                    rc.draw_indicator_dot(pos, 0, 150, 255)  # Friendly building - blue
            elif sense.is_enemy_building(pos):
                etype = sense.get_building_type(pos)
                if etype == EntityType.CORE:
                    rc.draw_indicator_dot(pos, 255, 0, 255)  # Enemy core - magenta
                elif etype in (EntityType.GUNNER, EntityType.SENTINEL, EntityType.BREACH):
                    rc.draw_indicator_dot(pos, 255, 100, 0)  # Enemy turret - orange
                elif etype == EntityType.ROAD:
                    rc.draw_indicator_dot(pos, 200, 200, 200)  # Enemy road - light gray
                elif etype == EntityType.MARKER:
                    rc.draw_indicator_dot(pos, 200, 200, 0)  # Enemy marker - dark yellow
                elif etype in (EntityType.CONVEYOR, EntityType.SPLITTER, EntityType.ARMOURED_CONVEYOR):
                    rc.draw_indicator_dot(pos, 150, 50, 50)  # Enemy logistics - dark red
                elif etype in (EntityType.HARVESTER, EntityType.FOUNDRY):
                    rc.draw_indicator_dot(pos, 255, 150, 50)  # Enemy economy - orange-red
                else:
                    rc.draw_indicator_dot(pos, 255, 0, 0)  # Enemy building - red
