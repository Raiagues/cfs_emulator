"""Session selection. Edit waveforms in each sensor's Python file."""
from sensors.session import run_session

# None includes every configured sensor. Use {"sensor_id": True} to select IDs.
SESSION = {'interval': 1,
 'sensors': None,
 'orbit': {'perigee': 548,
           'apogee': 552,
           'inclination': 97.59,
           'node': 212.9,
           'argument': 90,
           'anomaly': 0,
           'epoch': '2026-11-20T00:00:00Z',
           'model': 'J2'}}


if __name__ == "__main__":
    run_session()
