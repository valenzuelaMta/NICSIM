#!/usr/bin/env python3
"""
AttackerLatencyProxy.py

Simulates latency/jitter for selected sensor/actuator tags by scheduling
delayed writes of sampled values.

Behavior:
- For the chosen duration, repeatedly sample tags.
- For each sample, schedule a write at now + latency (+ jitter).
- Optionally drop some scheduled writes to emulate packet loss (drop probability).
- Logs one-line events to ./logs/attack-logs/log-latency-proxy-<ts>.txt
- Records a summary row in AttackerBase history (same as other attackers).

Notes:
- This approach simulates network/software-induced delay by overwriting tags later with
  stale values. It is non-invasive to the simulator code and works via existing _set/_receive API.
- Because it writes later, it may overwrite newer legitimate values — that's the point:
  it creates delayed/stale updates as if packets arrived out of order / delayed.
"""

import os
import time
import json
import logging
import random
from datetime import datetime, timedelta
from collections import deque

from AttackerBase import AttackerBase
from Configs import TAG


class AttackerLatencyProxy(AttackerBase):
    def __init__(self):
        super().__init__('attacker_latency_proxy')

        # prepare per-run logfile
        self.log_dir = os.path.join('.', 'logs', 'attack-logs')
        os.makedirs(self.log_dir, exist_ok=True)
        self.run_log = self.setup_logger(
            'latency_proxy_run',
            logging.Formatter('%(message)s'),
            file_dir=self.log_dir,
            file_ext='.txt'
        )
        self.run_log.info("timestamp,event,tag,scheduled_at,exec_at,latency_ms,jitter_ms,drop,notes")

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
        """Try to read a tag using _receive, fallback to _get."""
        try:
            v = self._receive(tag)
        except Exception:
            try:
                v = self._get(tag)
            except Exception:
                v = None
        return v

    def _logic(self):
        # 1) Choose targets (defaults like sensor spike attacker)
        default_targets = [
            TAG.TAG_CORE_TEMP_OUT_VALUE,
            TAG.TAG_CORE_PRESSURE_VALUE,
            TAG.TAG_CORE_FLOW_VALUE,
            TAG.TAG_SG_STEAM_PRESSURE_VALUE,
            TAG.TAG_SG_LEVEL_VALUE,
            TAG.TAG_SG_FEEDWATER_FLOW_VALUE,
        ]

        print("\nAvailable default targets (press Enter to accept defaults):")
        for i, t in enumerate(default_targets):
            print(f"  {i+1}) {t}")
        raw = self._prompt("Enter comma-separated tag names (or press Enter for defaults): ", "")
        if not raw:
            targets = default_targets.copy()
        else:
            targets = [x.strip() for x in raw.split(",") if x.strip()]

        # validate/expand shorthands
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

        # 3) Latency & jitter
        base_lat_ms = self._parse_float(self._prompt("Base latency ms (default 300): ", "300"), 300.0)
        jitter_ms = self._parse_float(self._prompt("Max jitter +/- ms (default 100): ", "100"), 100.0)

        # 4) Sampling cadence (how often we take a fresh sample per tag)
        sample_ms = self._parse_float(self._prompt("Sample interval ms (default 100): ", "100"), 100.0)

        # 5) Write cadence (we will check scheduled queue frequently; this is loop sleep)
        loop_sleep = self._parse_float(self._prompt("Internal loop sleep seconds (default 0.02): ", "0.02"), 0.02)

        # 6) Drop probability for scheduled writes (simulate loss)
        drop_prob = self._parse_float(self._prompt("Drop probability (0.0..1.0) default 0.0: ", "0.0"), 0.0)
        drop_prob = max(0.0, min(1.0, drop_prob))

        # summary
        self.report("=== Latency Proxy Test ===", logging.INFO)
        self.report(f"Targets: {valid}")
        self.report(f"Duration: {dur}s, base latency: {base_lat_ms} ms, jitter +/- {jitter_ms} ms")
        self.report(f"Sample interval: {sample_ms} ms, loop sleep: {loop_sleep}s, drop_prob: {drop_prob}")

        start = datetime.now()
        end_ts = start.timestamp() + dur
        self.attack_history.info(
            f"latency-proxy,{start.timestamp()},{(start + timedelta(seconds=dur)).timestamp()},{start},{start + timedelta(seconds=dur)},{self.MAC},{self.IP},latency-proxy"
        )
        self.run_log.info(f"{start.isoformat()},start,,{base_lat_ms},{jitter_ms},targets={json.dumps(valid)}")

        # scheduled write queue: store dicts: {exec_ts, tag, value, latency_ms, jitter_ms}
        scheduled = deque()

        # per-tag timer to control sampling cadence
        last_sample = {t: 0.0 for t in valid}
        now = time.time()
        last_loop = now

        try:
            while time.time() < end_ts:
                now = time.time()
                dt = now - last_loop
                last_loop = now

                # 1) sampling: for each tag, if sample_interval elapsed -> take snapshot, schedule write
                for t in valid:
                    if (now - last_sample[t]) * 1000.0 >= sample_ms:
                        last_sample[t] = now
                        cur = self._receive_safe(t)
                        # if None, skip
                        if cur is None:
                            self.run_log.info(f"{datetime.now().isoformat()},sample_none,{t},,,")
                            continue
                        # compute jittered latency
                        jitter = random.uniform(-jitter_ms, jitter_ms)
                        latency_ms = max(0.0, base_lat_ms + jitter)
                        exec_ts = now + (latency_ms / 1000.0)

                        # schedule write
                        scheduled.append({
                            "exec_ts": exec_ts,
                            "tag": t,
                            "value": cur,
                            "latency_ms": latency_ms,
                            "jitter_ms": jitter
                        })
                        self.run_log.info(f"{datetime.now().isoformat()},scheduled,{t},{datetime.fromtimestamp(exec_ts).isoformat()},{latency_ms},{jitter}")
                        # note: we do NOT write immediately; the scheduled time will apply the old sample later

                # 2) execute scheduled writes whose exec_ts <= now
                while scheduled and scheduled[0]["exec_ts"] <= now:
                    item = scheduled.popleft()
                    tag = item["tag"]
                    val = item["value"]
                    exec_ts = item["exec_ts"]
                    latency_ms = item["latency_ms"]
                    jitter = item["jitter_ms"]

                    # optionally drop
                    drop = False
                    if random.random() < drop_prob:
                        drop = True

                    if drop:
                        self.run_log.info(f"{datetime.now().isoformat()},dropped,{tag},{datetime.fromtimestamp(exec_ts).isoformat()},{latency_ms},{jitter}")
                        # simulate dropped packet by not writing
                        continue

                    # perform write (stale value)
                    try:
                        self._set(tag, val)
                        self.run_log.info(f"{datetime.now().isoformat()},exec,{tag},{datetime.fromtimestamp(exec_ts).isoformat()},{latency_ms},{jitter},written")
                    except Exception as e:
                        self.run_log.info(f"{datetime.now().isoformat()},exec_error,{tag},{datetime.fromtimestamp(exec_ts).isoformat()},{latency_ms},{jitter},err:{e}")
                        self.report(f"Failed scheduled write for {tag}: {e}", logging.ERROR)

                # small sleep to keep loop sane
                time.sleep(loop_sleep)

        except KeyboardInterrupt:
            self.report("Interrupted by user", logging.WARNING)

        # Finish: log summary and return
        end = datetime.now()
        self.run_log.info(f"{end.isoformat()},finish,,{base_lat_ms},{jitter_ms},remaining_scheduled={len(scheduled)}")
        self.report("Latency proxy test finished.", logging.INFO)
        return


if __name__ == "__main__":
    attacker = AttackerLatencyProxy()
    attacker.start()
