from cambc import Controller, Environment, Position, EntityType
from typing import Optional, List

class Sense:
    """Persistent map knowledge stored as a grid."""
    # Grid: None=unknown,
    # 0=empty,
    # 1=wall,
    # 2=ore_titanium,
    # 3=ore_axionite
    # >=4 = building (positive=friendly, negative=enemy), actual_id (if any) = abs(stored_val) - 4
    def __init__(self, rc: Controller):
        self.rc = rc
        self.width = rc.get_map_width()
        self.height = rc.get_map_height()
        
        self._grid: List[List[Optional[int]]] = [
            [None for _ in range(self.width)] 
            for _ in range(self.height)
        ]
    
    def update(self) -> None:
        """Refresh knowledge from current vision. Call each frame."""
        my_team = self.rc.get_team()
        for pos in self.rc.get_nearby_tiles():
            self._update_tile(pos, my_team)
    
    def _update_tile(self, pos: Position, my_team: int) -> None:
        """Update grid entry for a visible tile."""
        building_id = self.rc.get_tile_building_id(pos)
        if building_id is not None:
            stored_id = building_id + 4
            if self.rc.get_team(building_id) == my_team:
                self._grid[pos.y][pos.x] = stored_id  # Friendly
            else:
                self._grid[pos.y][pos.x] = -stored_id  # Enemy
            return
        
        env = self.rc.get_tile_env(pos)
        if env == Environment.WALL:
            self._grid[pos.y][pos.x] = 1
        elif env == Environment.ORE_TITANIUM:
            self._grid[pos.y][pos.x] = 2
        elif env == Environment.ORE_AXIONITE:
            self._grid[pos.y][pos.x] = 3
        elif env == Environment.EMPTY:
            self._grid[pos.y][pos.x] = 0
    
    # === Query ===
    def get_entity_id(self, pos: Position) -> Optional[int]:
        """Get building entity ID at position (None if not a building)."""
        if not (0 <= pos.x < self.width and 0 <= pos.y < self.height):
            return None

        val = self._grid[pos.y][pos.x]
        if val is None:
            return None
        if val < 4 and val >= 0:
            return val
        return abs(val) - 4  # Convert back to actual game ID
    
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
        return val is not None and val >= 4
    
    def is_enemy_building(self, pos: Position) -> bool:
        if not (0 <= pos.x < self.width and 0 <= pos.y < self.height):
            return False
        val = self._grid[pos.y][pos.x]
        return val is not None and val <= -4
