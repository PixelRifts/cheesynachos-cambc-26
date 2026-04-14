import random
import sys

from enum import Enum
from bot import Bot
from cambc import Controller, Direction, EntityType, Environment, Position, GameConstants
from helpers import DIRECTIONS

# Priority map for targeting
PRIORITIES = {
    EntityType.BUILDER_BOT: 60,
    EntityType.CORE: 500,
    EntityType.GUNNER: 100,
    EntityType.SENTINEL: 100,
    EntityType.BREACH: 100,
    EntityType.LAUNCHER: 100,
    EntityType.CONVEYOR: 10,
    EntityType.SPLITTER: 20,
    EntityType.ARMOURED_CONVEYOR: 10,
    EntityType.BRIDGE: 10,
    EntityType.HARVESTER: -100,
    EntityType.FOUNDRY: 100,
    EntityType.ROAD: 1,
    EntityType.BARRIER: 1,
    EntityType.MARKER: 1,
}

class Gunner(Bot):
    def __init__(self, rc: Controller):
        super().__init__(rc)
        self.best_target = None
        self.attack_dmg = GameConstants.SENTINEL_DAMAGE

    def is_path_clear(self, target_pos: Position) -> bool:
      my_pos = self.rc.get_position()
    
      # Determine the direction of movement per axis(-1, 0, or 1)
      def get_step(start, end):
          if start == end: return 0
          return 1 if end > start else -1

      step_x = get_step(my_pos.x, target_pos.x)
      step_y = get_step(my_pos.y, target_pos.y)
      dist = max(abs(target_pos.x - my_pos.x), abs(target_pos.y - my_pos.y))
      for i in range(1, dist): 
          check_x = my_pos.x + (i * step_x)
          check_y = my_pos.y + (i * step_y)
          p = Position(check_x, check_y)

          bid = self.rc.get_tile_building_id(p)
          env = self.rc.get_tile_env(p)
          if env == Environment.WALL:
              return False
          if bid is not None:
              ent_type = self.rc.get_entity_type(bid)
              # print(ent_type)
              if ent_type not in [EntityType.ROAD, EntityType.MARKER]:
                  return False

      return True

    def get_best_in_range(self, candidates):
        best_tile = None
        max_priority = 0

        for p in candidates:
            e = self.rc.get_tile_building_id(p)
            bb = self.rc.get_tile_builder_bot_id(p)

            current_tile_priority = -float('inf')

            if bb is not None and self.rc.get_team(bb) != self.rc.get_team():
                current_tile_priority = PRIORITIES.get(EntityType.BUILDER_BOT, 0)

            if e is not None and self.rc.get_team(e) != self.rc.get_team():
                entt = self.rc.get_entity_type(e)
                building_priority = PRIORITIES.get(entt, 0)
                current_tile_priority = max(current_tile_priority, building_priority)

            # Update best if this tile is the new maximum and we can actually fire there
            if current_tile_priority > max_priority and self.is_path_clear(p):
                max_priority = current_tile_priority
                best_tile = p

        return best_tile, max_priority

    def start_turn(self):
        # Reset target at the start of every turn to avoid stale data
        self.best_target = None
        
        best_overall_priority = -float('inf')
        best_direction = None
        found_target = None

        # Iterate through all directions to see where the best target lies
        for d in DIRECTIONS:
            tiles = self.rc.get_attackable_tiles_from(self.rc.get_position(), d, EntityType.GUNNER)
            if not tiles:
                continue

            tile, priority = self.get_best_in_range(tiles)
            
            if tile and priority > best_overall_priority:
                best_overall_priority = priority
                best_direction = d
                found_target = tile

        if found_target:
            self.best_target = found_target
            self.rc.draw_indicator_dot(self.best_target, 0, 0, 255)

        # 2. Rotate to face the best target if necessary
        if best_direction is not None and best_direction != self.rc.get_direction():
            if self.rc.can_rotate(best_direction) and self.rc.get_ammo_amount() != 0:
                self.rc.rotate(best_direction)

    # def turn(self):
    #     target  = self.rc.get_gunner_target()
    #     if target and self.rc.can_fire(target):
    #         self.rc.fire(target)
    #     pass

    def turn(self):
        # If no target was found in start_turn, don't attempt to fire
        if not self.best_target:
            return

        target = self.rc.get_gunner_target()
        if not target:
            return
        if self.rc.can_fire(target):
            bb = self.rc.get_tile_builder_bot_id(target)
            if bb is not None and self.rc.get_team(bb) == self.rc.get_team():
                return
            e = self.rc.get_tile_building_id(target)
            if e is not None and self.rc.get_team(e) == self.rc.get_team() and not (bb is not None and self.rc.get_team(bb) != self.rc.get_team()):
                print('this condition')
                return
            self.rc.fire(target)

    def end_turn(self):
        pass
