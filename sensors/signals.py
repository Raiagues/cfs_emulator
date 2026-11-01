"""Session selection. Edit waveforms in each sensor's Python file."""
from sensors.session import run_session

# None includes every configured sensor. Use {"sensor_id": True} to select IDs.
SESSION = {"interval": 1.0, "sensors": None}


if __name__ == "__main__":
    run_session()
