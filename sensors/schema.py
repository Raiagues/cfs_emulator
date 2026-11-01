"""Configuration shared by editable sensor models and the QMP runner."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Signal:
    property: str
    unit: str
    scale: int


@dataclass(frozen=True)
class Sensor:
    model: str
    bus: str
    address: int
    qom_path: str
    signals: tuple[Signal, ...]

    @classmethod
    def from_device(cls, device, signals):
        return cls(device["model"], device["bus"], device["address"],
                   f"/machine/peripheral/{device['id']}", tuple(signals))
