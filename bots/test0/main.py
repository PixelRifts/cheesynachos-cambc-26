"""Move-only wanderer test bot.

Core spawns a few builder bots.
Builder bots only attempt random movement each turn.
No harvesting, no markers, and no building.
"""

import random

from cambc import Controller, Direction, EntityType

DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]


class Player:
    def __init__(self):
        self.num_spawned = 0 #no of builders spawned
        self.max_spawned = 3

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()

        if etype == EntityType.CORE:
            if self.num_spawned < self.max_spawned:
                spawn_pos = ct.get_position().add(random.choice(DIRECTIONS))
                if ct.can_spawn(spawn_pos):
                    ct.spawn_builder(spawn_pos)
                    self.num_spawned += 1
            return

        if etype == EntityType.BUILDER_BOT:
            move_dir = random.choice(DIRECTIONS)
            if ct.can_move(move_dir):
                ct.move(move_dir)
