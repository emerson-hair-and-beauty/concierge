from pydantic import BaseModel

class OrchestratorInput(BaseModel):
    porosity: str
    scalp: str
    damage: str
    density: str
    texture: str
