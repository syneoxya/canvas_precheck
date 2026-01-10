from typing import Protocol

class Agent(Protocol):
    name: str
    def run(self, state: dict) -> dict: ...

class Pipeline:
    def __init__(self, agents: list[Agent]):
        self.agents = agents

    def run(self, state: dict) -> dict:
        for agent in self.agents:
            state = agent.run(state)
        return state