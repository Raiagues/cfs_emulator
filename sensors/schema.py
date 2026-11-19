"""Configuration shared by editable sensor models and the QMP runner."""
from dataclasses import dataclass
from pathlib import Path


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

    @classmethod
    def from_model(cls, device, waveform_file):
        from project.sensor_models import display_units, load, model_paths
        root = Path(waveform_file).resolve().parents[1]
        spec = load(model_paths(root)[device["model"]])
        signals = []
        for output in spec["outputs"]:
            scale, unit = display_units(output["unit"])
            signals.append(Signal(output["name"], unit, scale))
        return cls.from_device(device, signals)
