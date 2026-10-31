"""Sensor waveforms and scheduling are checked without a running emulator."""

import contextlib
import copy
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sensors import lsm303dlhc_mag, simulator, tmp105


def device(sensor_id="temp0", model="tmp105", values=None, address=0x48):
    return {
        "name": sensor_id, "id": sensor_id, "model": model,
        "bus": "i2c-bus.1", "address": address,
        "values": {"temperature": 23500} if values is None else values,
    }


def config(devices):
    return {"schema_version": 1, "board": "raspi4b", "os": "raspios", "devices": devices, "apps": []}


class WaveformTests(unittest.TestCase):
    def test_tmp105_preserves_zero_and_negative_baselines(self):
        for baseline in (0, -10000, 23500):
            with self.subTest(baseline=baseline):
                initial = {"temperature": baseline}
                self.assertEqual(tmp105.sample(0, initial), initial)
                self.assertEqual(tmp105.sample(tmp105.PERIOD_SECONDS / 4, initial),
                                 {"temperature": baseline + round(tmp105.AMPLITUDE_C * 1000)})
                self.assertEqual(tmp105.sample(3 * tmp105.PERIOD_SECONDS / 4, initial),
                                 {"temperature": baseline - round(tmp105.AMPLITUDE_C * 1000)})
                self.assertEqual(initial, {"temperature": baseline})

    def test_defaults_and_python_parameters_control_temperature(self):
        with patch.object(tmp105, "DEFAULT_C", -2.0), \
                patch.object(tmp105, "AMPLITUDE_C", 1.25), \
                patch.object(tmp105, "PERIOD_SECONDS", 8.0):
            self.assertEqual(tmp105.sample(0, {}), {"temperature": -2000})
            self.assertEqual(tmp105.sample(2, {}), {"temperature": -750})
            self.assertEqual(tmp105.sample(6, {}), {"temperature": -3250})

    def test_magnetometer_uses_each_axis_baseline_and_units(self):
        initial = {"mag-x": -10000, "mag-y": 0, "mag-z": 45000}
        amplitude = round(lsm303dlhc_mag.AMPLITUDE_UT * 1000)
        self.assertEqual(lsm303dlhc_mag.sample(0, initial),
                         {"mag-x": -10000 + amplitude, "mag-y": 0, "mag-z": 45000})
        self.assertEqual(lsm303dlhc_mag.sample(lsm303dlhc_mag.PERIOD_SECONDS / 4, initial),
                         {"mag-x": -10000, "mag-y": amplitude, "mag-z": 45000})
        self.assertEqual(initial, {"mag-x": -10000, "mag-y": 0, "mag-z": 45000})

    def test_invalid_python_periods_are_reported(self):
        for adapter in (tmp105, lsm303dlhc_mag):
            for period in (0, -1, float("inf"), float("nan")):
                with self.subTest(model=adapter.DEVICE, period=period), \
                        patch.object(adapter, "PERIOD_SECONDS", period):
                    with self.assertRaisesRegex(ValueError, "PERIOD_SECONDS"):
                        adapter.sample(0, {})

    def test_two_instances_keep_independent_initial_values(self):
        sensors = [device(values={"temperature": -5000}),
                   device("temp1", values={"temperature": 30000}, address=0x49)]
        before = copy.deepcopy(sensors)
        frame = simulator.sample_values(sensors, tmp105.PERIOD_SECONDS / 4)
        self.assertEqual([(item[0]["id"], item[1]["temperature"]) for item in frame],
                         [("temp0", 0), ("temp1", 35000)])
        self.assertEqual(sensors, before)

    def test_user_waveform_cannot_mutate_stored_project_values(self):
        sensor = device()

        def sample(elapsed, initial):
            initial["temperature"] = 10000
            return initial

        with patch.object(tmp105, "sample", side_effect=sample):
            frame = simulator.sample_values([sensor], 0)
        self.assertEqual(frame[0][1], {"temperature": 10000})
        self.assertEqual(sensor["values"], {"temperature": 23500})

    def test_frame_routes_models_by_device_model(self):
        sensors = [device(), device("mag0", "lsm303dlhc_mag", {"mag-z": 12345}, 0x1E)]
        frame = simulator.sample_values(sensors, 0)
        self.assertEqual(frame[0][1], {"temperature": 23500})
        self.assertEqual(set(frame[1][1]), {"mag-x", "mag-y", "mag-z"})
        self.assertEqual(frame[1][1]["mag-z"], 12345)

    def test_invalid_sample_is_rejected_before_transport(self):
        invalid = ({}, {"temperature": True}, {"temperature": 1.5},
                   {"temperature": float("nan")}, {"temperature": 128000},
                   {"temperature": -128001}, {"missing_property": 0}, None)
        for sample in invalid:
            with self.subTest(sample=sample), patch.object(tmp105, "sample", return_value=sample):
                with self.assertRaises(ValueError):
                    simulator.sample_values([device()], 0)

    def test_boundaries_are_accepted_without_clamping(self):
        for temperature in (-128000, 0, 127937):
            with self.subTest(temperature=temperature), \
                    patch.object(tmp105, "sample", return_value={"temperature": temperature}):
                frame = simulator.sample_values([device()], 0)
                self.assertEqual(frame[0][1]["temperature"], temperature)

    def test_unknown_model_is_not_treated_as_temperature(self):
        with self.assertRaises(ValueError):
            simulator.sample_values([device(model="unknown_sensor")], 0)


class Clock:
    def __init__(self):
        self.now = 100.0
        self.delays = []

    def monotonic(self):
        return self.now

    def sleep(self, delay):
        self.delays.append(delay)
        self.now += delay


class SimulatorTests(unittest.TestCase):
    def run_simulation(self, devices, ids=(), **kwargs):
        board = Mock()
        connection = Mock()
        connection.__enter__ = Mock(return_value=board)
        connection.__exit__ = Mock(return_value=False)
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        self.load = stack.enter_context(patch.object(simulator, "load_config", return_value=config(devices)))
        self.record = stack.enter_context(patch.object(simulator, "check_record"))
        self.live = stack.enter_context(patch.object(simulator, "check_live"))
        self.connect = stack.enter_context(patch.object(simulator, "connect_board", return_value=connection))
        self.write = stack.enter_context(patch.object(simulator, "set_property"))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        simulator.simulate(Path("/test/project"), ids, **kwargs)
        return board

    def test_selected_id_only_is_written(self):
        sensors = [device(), device("temp1", values={"temperature": -5000}, address=0x49)]
        self.run_simulation(sensors, ("temp1",), steps=1)
        self.assertEqual(self.write.call_count, 1)
        self.assertEqual(self.write.call_args.args[1:3], ("/machine/peripheral/temp1", "temperature"))
        self.record.assert_called_once()
        self.live.assert_called()

    def test_invalid_ids_and_empty_project_never_connect(self):
        for sensors, ids in (([device()], ("missing",)), ([device()], ("temp0", "temp0")), ([], ())):
            with self.subTest(ids=ids, sensors=sensors):
                with self.assertRaises(ValueError):
                    self.run_simulation(sensors, ids, steps=1)
                self.connect.assert_not_called()
                self.write.assert_not_called()

    def test_invalid_frame_sends_no_partial_sensor_updates(self):
        sensors = [device(), device("temp1", address=0x49)]
        with patch.object(tmp105, "sample", side_effect=[{"temperature": 23500}, {"temperature": 128000}]):
            with self.assertRaises(ValueError):
                self.run_simulation(sensors, steps=1)
        self.write.assert_not_called()

    def test_live_mismatch_prevents_writes(self):
        with patch.object(simulator, "check_live", side_effect=ValueError("changed board")):
            # Install the other mocks without replacing this failure.
            with patch.object(simulator, "load_config", return_value=config([device()])), \
                    patch.object(simulator, "check_record"), \
                    patch.object(simulator, "connect_board") as connect, \
                    patch.object(simulator, "set_property") as write:
                with self.assertRaisesRegex(ValueError, "changed board"):
                    simulator.simulate(Path("/test/project"), steps=1)
                write.assert_not_called()
                connect.return_value.__exit__.assert_called_once()

    def test_bounded_loop_uses_elapsed_seconds_and_compensates_io_time(self):
        clock = Clock()
        samples = []

        def sample(elapsed, initial):
            samples.append(elapsed)
            return {"temperature": 23500}

        def write(*args):
            clock.now += 0.2

        with patch.object(simulator.time, "monotonic", side_effect=clock.monotonic), \
                patch.object(simulator.time, "sleep", side_effect=clock.sleep), \
                patch.object(tmp105, "sample", side_effect=sample), \
                patch.object(simulator, "load_config", return_value=config([device()])), \
                patch.object(simulator, "check_record"), patch.object(simulator, "check_live"), \
                patch.object(simulator, "connect_board"), \
                patch.object(simulator, "set_property", side_effect=write) as transport, \
                contextlib.redirect_stdout(io.StringIO()):
            simulator.simulate(Path("/test/project"), interval=1.0, steps=3)
        self.assertEqual(transport.call_count, 3)
        self.assertEqual(samples, [0.0, 1.0, 2.0])
        self.assertEqual(len(clock.delays), 2)
        for delay in clock.delays:
            self.assertAlmostEqual(delay, 0.8)

    def test_invalid_timing_is_rejected_before_connect(self):
        for settings in ({"interval": 0}, {"interval": -1}, {"interval": float("inf")},
                         {"interval": float("nan")}, {"steps": 0}, {"steps": -1}):
            with self.subTest(settings=settings):
                with self.assertRaises(ValueError):
                    self.run_simulation([device()], **settings)
                self.connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
