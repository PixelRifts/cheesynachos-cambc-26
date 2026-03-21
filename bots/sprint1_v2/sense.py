from cambc import Controller, Environment, Position, EntityType
from typing import Optional, List

_BUILDING_OFFSET = 4

_ENTITY_TYPE_TO_VALUE = {
    EntityType.CORE: 4,
    EntityType.GUNNER: 5,
    EntityType.SENTINEL: 6,
    EntityType.BREACH: 7,
    EntityType.LAUNCHER: 8,
    EntityType.CONVEYOR: 9,
    EntityType.SPLITTER: 10,
    EntityType.ARMOURED_CONVEYOR: 11,
    EntityType.BRIDGE: 12,
    EntityType.HARVESTER: 13,
    EntityType.FOUNDRY: 14,
    EntityType.ROAD: 15,
    EntityType.BARRIER: 16,
    EntityType.MARKER: 17,
}

_VALUE_TO_ENTITY_TYPE = {v: k for k, v in _ENTITY_TYPE_TO_VALUE.items()}

class Sense:
    """Persistent map knowledge stored as a grid."""
    
    def __init__(self, rc: Controller):
        self.rc = rc
        self.width = rc.get_map_width()
        self.height = rc.get_map_height()

        self.nearest_enemy_infra_dist = float('inf')
        self.nearest_enemy_infra: Position = None
        self.nearest_bridge_dist = float('inf')
        self.nearest_bridge: Position = None
        self.nearest_ore_dist = float('inf')
        self.nearest_ore: Position = None
        
        # Grid: None=unknown, 0=empty, 1=wall, 2=ore_titanium, 3=ore_axionite
        # 4-17 = friendly buildings, -4 to -17 = enemy buildings
        self._grid: List[List[Optional[int]]] = [
            [None for _ in range(self.width)] 
            for _ in range(self.height)
        ]
    
    def update(self) -> None:
        """Refresh knowledge from current vision. Call each frame."""
        my_team = self.rc.get_team()
        self.nearest_ore_dist = float('inf')
        self.nearest_ore = None
        self.nearest_enemy_infra_dist = float('inf')
        self.nearest_enemy_infra: Position = None
        self.nearest_bridge_dist = float('inf')
        self.nearest_bridge = None
        for pos in self.rc.get_nearby_tiles():
            self._update_tile(pos, my_team)
    
    def _update_tile(self, pos: Position, my_team: int) -> None:
        """Update grid entry for a visible tile."""
        building_id = self.rc.get_tile_building_id(pos)
        if building_id is not None:
            entity_type = self.rc.get_entity_type(building_id)
            
            # Mark nearest bridge
            p = self.rc.get_position(building_id)
            d = p.distance_squared(self.rc.get_position())
            if entity_type == EntityType.BRIDGE:
                if self.rc.get_team(building_id) == self.rc.get_team():
                    if d < self.nearest_bridge_dist:
                        self.nearest_bridge_dist = d
                        self.nearest_bridge = p
                else:
                    if d < self.nearest_enemy_infra_dist:
                        self.nearest_enemy_infra_dist = d
                        self.nearest_enemy_infra = p
            elif entity_type == EntityType.CONVEYOR:
                if self.rc.get_team(building_id) != self.rc.get_team():
                    if d < self.nearest_enemy_infra_dist:
                        self.nearest_enemy_infra_dist = d
                        self.nearest_enemy_infra = p

            stored_val = _ENTITY_TYPE_TO_VALUE.get(entity_type)
            if stored_val is not None:
                if self.rc.get_team(building_id) == my_team:
                    self._grid[pos.y][pos.x] = stored_val  # Friendly
                else:
                    self._grid[pos.y][pos.x] = -stored_val  # Enemy
            return
        
        env = self.rc.get_tile_env(pos)
        dist = self.rc.get_position().distance_squared(pos)
        if env == Environment.WALL:
            self._grid[pos.y][pos.x] = 1
        elif env == Environment.ORE_TITANIUM:
            self._grid[pos.y][pos.x] = 2
            # Mark nearest Ore
            if dist < self.nearest_ore_dist:
                self.nearest_ore_dist = dist
                self.nearest_ore = pos
        elif env == Environment.ORE_AXIONITE:
            self._grid[pos.y][pos.x] = 3
            # Mark nearest Ore
            if dist < self.nearest_ore_dist:
                self.nearest_ore_dist = dist
                self.nearest_ore = pos
        elif env == Environment.EMPTY:
            self._grid[pos.y][pos.x] = 0
    
    # === Query ===
    def get_entity_id(self, pos: Position) -> Optional[int]:
        """Get building type value at position (None if not a building)."""
        if not (0 <= pos.x < self.width and 0 <= pos.y < self.height):
            return None
        val = self._grid[pos.y][pos.x]
        if val is None or val in (0, 1, 2, 3):
            return None
        return abs(val)
    
    def get_building_type(self, pos: Position) -> Optional[EntityType]:
        """Get EntityType of building at position (None if not a building)."""
        val = self.get_entity_id(pos)
        if val is None:
            return None
        return _VALUE_TO_ENTITY_TYPE.get(val)
    
    def is_wall(self, pos: Position) -> bool:
        return self._grid[pos.y][pos.x] == 1 if (0 <= pos.x < self.width and 0 <= pos.y < self.height) else False
    
    def is_ore_titanium(self, pos: Position) -> bool:
        return self._grid[pos.y][pos.x] == 2 if (0 <= pos.x < self.width and 0 <= pos.y < self.height) else False
    
    def is_ore_axionite(self, pos: Position) -> bool:
        return self._grid[pos.y][pos.x] == 3 if (0 <= pos.x < self.width and 0 <= pos.y < self.height) else False
    
    def is_empty(self, pos: Position) -> bool:
        return self._grid[pos.y][pos.x] == 0 if (0 <= pos.x < self.width and 0 <= pos.y < self.height) else False
    
    def is_unknown(self, pos: Position) -> bool:
        if not (0 <= pos.x < self.width and 0 <= pos.y < self.height):
            return True
        return self._grid[pos.y][pos.x] is None
    
    def is_building(self, pos: Position) -> bool:
        if not (0 <= pos.x < self.width and 0 <= pos.y < self.height):
            return False
        val = self._grid[pos.y][pos.x]
        if val is None or val in (0, 1, 2, 3):
            return False
        return True
    
    def is_friendly_building(self, pos: Position) -> bool:
        if not (0 <= pos.x < self.width and 0 <= pos.y < self.height):
            return False
        val = self._grid[pos.y][pos.x]
        return val is not None and val >= _BUILDING_OFFSET
    
    def is_enemy_building(self, pos: Position) -> bool:
        if not (0 <= pos.x < self.width and 0 <= pos.y < self.height):
            return False
        val = self._grid[pos.y][pos.x]
        return val is not None and val <= -_BUILDING_OFFSET
