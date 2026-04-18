
from cambc import Controller, Direction, EntityType, Environment, Position

class Bot:
    def __init__(self, rc: Controller):
        self.rc = rc
    
    def start_turn(self):
        print("Default Start turn behaviour")

    def turn(self):
        print("Turn behaviour")

    def end_turn(self):
        print("Default End turn behaviour")