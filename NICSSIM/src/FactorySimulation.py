# FactorySimulation.py
import logging
import random
import os
import json
from datetime import datetime, timedelta

from ics_sim.Device import HIL
from Configs import TAG, PHYSICS, Connection


class FactorySimulation(HIL):
    def __init__(self):
        super().__init__('Factory', Connection.CONNECTION, 100)  # 100 ms loop

        # ---------- one-line file logger (same style/location as HMI1) ----------
        os.makedirs("src/logs", exist_ok=True)
        self._sensor_logger = logging.getLogger("FACTORY_SENSORS")
        self._sensor_logger.setLevel(logging.INFO)
        if not any(isinstance(h, logging.FileHandler) and getattr(h, "_factory_handler", False)
                   for h in self._sensor_logger.handlers):
            log_path = os.getenv("SENSOR_LOG_PATH", "src/logs/logs-Factory.log")
            fh = logging.FileHandler(log_path, mode="a", encoding="utf-8")
            fh._factory_handler = True
            fh.setLevel(logging.INFO)
            fh.setFormatter(logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] FACTORY: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            ))
            self._sensor_logger.addHandler(fh)
            # first line to confirm path
            self._sensor_logger.info(f"SENSOR LOG FILE → {log_path}")

        # Log every N loops (default 1 = every 100 ms)
        try:
            self._log_every = max(1, int(os.getenv("SENSOR_LOG_EVERY", "1")))
        except Exception:
            self._log_every = 1
        self._loop_idx = 0

        # Round numbers for readability
        self._round_enabled = os.getenv("SENSOR_LOG_ROUND", "1") not in ("0", "false", "False")

        self.init()

    # ------------------------------
    # Core simulation logic
    # ------------------------------
    def _logic(self):
        dt = self._current_loop_time - self._last_loop_time  # ms
        if dt <= 0:
            dt = 1
        dt_s = dt / 1000.0

        # =========================
        # Read current primary state
        # =========================
        flux     = self._get(TAG.TAG_CORE_NEUTRON_FLUX_VALUE)
        temp_in  = self._get(TAG.TAG_CORE_TEMP_IN_VALUE)
        temp_out = self._get(TAG.TAG_CORE_TEMP_OUT_VALUE)
        pressure = self._get(TAG.TAG_CORE_PRESSURE_VALUE)
        flow     = self._get(TAG.TAG_CORE_FLOW_VALUE)

        # Primary commands / setpoints
        rcp_cmd      = self._get(TAG.TAG_CORE_RCP_SPEED_CMD)             # 0..1
        cool_valve   = self._get(TAG.TAG_CORE_COOLANT_VALVE_CMD)         # 0..1
        loop_valve   = self._get(TAG.TAG_PRIMARY_LOOP_VALVE_CMD)         # 0..1
        rod_pos      = self._get(TAG.TAG_CORE_CONTROL_ROD_POS_VALUE)     # %
        flux_sp      = self._get(TAG.TAG_CORE_NEUTRON_FLUX_SP)           # a.u.

        # Pressurizer actions
        heater_cmd   = self._get(TAG.TAG_CORE_PRESSURIZER_HEATER_CMD)    # 0..1
        spray_cmd    = self._get(TAG.TAG_CORE_PRESSURIZER_SPRAY_CMD)     # 0..1
        relief_open  = 1.0 if self._get(TAG.TAG_CORE_RELIEF_VALVE_STATUS) else 0.0

        # =========================
        # Read current secondary state
        # =========================
        sg_sec_t_in   = self._get(TAG.TAG_SG_SEC_TEMP_IN_VALUE)          # °C
        sg_sec_t_out  = self._get(TAG.TAG_SG_SEC_TEMP_OUT_VALUE)         # °C
        sg_p          = self._get(TAG.TAG_SG_STEAM_PRESSURE_VALUE)       # MPa
        sg_level      = self._get(TAG.TAG_SG_LEVEL_VALUE)                # %
        sg_relief     = 1.0 if self._get(TAG.TAG_SG_RELIEF_VALVE_STATUS) else 0.0

        # Secondary commands
        sg_fw_cmd     = self._get(TAG.TAG_SG_FEEDWATER_VALVE_CMD)        # 0..1

        # =========================
        # PRIMARY: actuator dynamics
        # =========================
        flow += (rcp_cmd - flow) * (PHYSICS.FLOW_INERTIA * dt)

        self._cool_valve_eff = self._clamp01(
            self._cool_valve_eff + (cool_valve - self._cool_valve_eff) * (PHYSICS.VALVE_INERTIA * dt)
        )
        self._loop_valve_eff = self._clamp01(
            self._loop_valve_eff + (loop_valve - self._loop_valve_eff) * (PHYSICS.VALVE_INERTIA * dt)
        )

        # Provide a measured position for the loop valve
        self._set(TAG.TAG_PRIMARY_LOOP_VALVE_POS_VALUE, self._loop_valve_eff)

        # Reactivity / flux
        reactivity = max(0.05, 1.0 - (rod_pos / 120.0))
        flux_target = max(0.0, flux_sp * reactivity)
        flux += (flux_target - flux) * (PHYSICS.FLUX_INERTIA * dt)
        flux = max(0.0, flux + random.gauss(0, 0.002))

        # Thermal balance on primary
        effective_cooling_valve = self._cool_valve_eff * self._loop_valve_eff
        heat_gain = PHYSICS.HEAT_GAIN_K * flux * dt
        cool_loss = (
            PHYSICS.COOlING_K * (flow * effective_cooling_valve) * max(0.0, (temp_out - PHYSICS.AMBIENT_TEMP)) * dt
            if hasattr(PHYSICS, 'COOlING_K')
            else PHYSICS.COOLING_K * (flow * effective_cooling_valve) * max(0.0, (temp_out - PHYSICS.AMBIENT_TEMP)) * dt
        )

        temp_in += (PHYSICS.AMBIENT_TEMP - temp_in) * 0.001 * dt
        temp_out = temp_out + heat_gain - cool_loss
        temp_out += random.gauss(0, 0.02)

        pressure_base = 14.7 + PHYSICS.PRESSURE_K_TEMP * max(0.0, (temp_out - PHYSICS.AMBIENT_TEMP))
        pressure += (PHYSICS.PRESSURE_K_HEATER * heater_cmd * dt_s)
        pressure -= (PHYSICS.PRESSURE_K_SPRAY  * spray_cmd  * dt_s)
        pressure -= (PHYSICS.PRESSURE_K_RELIEF * relief_open * dt_s)
        pressure = 0.98 * pressure + 0.02 * pressure_base
        pressure += random.gauss(0, 0.002)

        sg_in_p = max(0.0, pressure - 0.05 + random.gauss(0, 0.001))

        # Radiation transient (rare spikes)
        now = datetime.now()
        if (not self._rad_spike['active']) and random.random() < PHYSICS.RAD_SPIKE_PROB:
            self._rad_spike['active'] = True
            sec = random.uniform(*PHYSICS.RAD_SPIKE_SEC)
            self._rad_spike['until'] = now + timedelta(seconds=sec)
            self._rad_spike['level'] = random.uniform(PHYSICS.RAD_BASELINE*2, PHYSICS.RAD_SPIKE_MAX)
        if self._rad_spike['active'] and now >= self._rad_spike['until']:
            self._rad_spike['active'] = False
        rad = self._rad_spike['level'] if self._rad_spike['active'] else PHYSICS.RAD_BASELINE
        rad += random.gauss(0, 0.005)
        rad = max(0.0, rad)

        flow = self._clamp(flow, 0.0, 1.2)

        # =========================
        # SECONDARY (Steam Generator)
        # =========================
        target_fw_flow = 0.02 + 0.98 * self._clamp01(sg_fw_cmd)    # 0.02..1.0
        self._sg_fw_meas += (target_fw_flow - self._sg_fw_meas) * (PHYSICS.VALVE_INERTIA * dt)
        self._sg_fw_meas = self._clamp01(self._sg_fw_meas)

        sg_sec_t_in += (PHYSICS.SG_SEC_FEEDWATER_TEMP - sg_sec_t_in) * 0.002 * dt

        hx_gain = PHYSICS.SG_HX_K * max(0.0, temp_out - sg_sec_t_in) * (flow * effective_cooling_valve) * dt
        sg_sec_t_out = sg_sec_t_out + hx_gain + random.gauss(0, 0.02)
        sg_sec_t_out = min(sg_sec_t_out, temp_out)
        sg_sec_t_out = max(sg_sec_t_out, sg_sec_t_in)

        steam_prod = max(0.0, sg_sec_t_out - sg_sec_t_in) * self._sg_fw_meas

        sg_level += (
            + 50.0 * self._sg_fw_meas
            - 100.0 * PHYSICS.SG_BOIL_OFF_K * steam_prod
        ) * (PHYSICS.SG_LEVEL_INERTIA * dt)
        sg_level += random.gauss(0, 0.02)
        sg_level = self._clamp(sg_level, 0.0, 100.0)

        sg_p += (PHYSICS.SG_PRESSURE_K * steam_prod * dt_s)
        sg_p -= (PHYSICS.SG_PRESSURE_RELIEF_K * sg_relief * dt_s)
        sg_p += random.gauss(0, 0.005)
        sg_p = max(0.0, sg_p)

        if (not self._sg_leak_spike['active']) and random.random() < 0.0002:
            self._sg_leak_spike['active'] = True
            sec = random.uniform(2, 8)
            self._sg_leak_spike['until'] = now + timedelta(seconds=sec)
            self._sg_leak_spike['level'] = random.uniform(0.02, 0.20)  # µSv/h
        if self._sg_leak_spike['active'] and now >= self._sg_leak_spike['until']:
            self._sg_leak_spike['active'] = False
        sg_leak = self._sg_leak_spike['level'] if self._sg_leak_spike['active'] else 0.0
        sg_leak = max(0.0, sg_leak + random.gauss(0, 0.003))

        # =========================
        # Write back sensors
        # =========================
        self._set(TAG.TAG_CORE_NEUTRON_FLUX_VALUE, flux)
        self._set(TAG.TAG_CORE_TEMP_IN_VALUE,      temp_in)
        self._set(TAG.TAG_CORE_TEMP_OUT_VALUE,     temp_out)
        self._set(TAG.TAG_CORE_PRESSURE_VALUE,     pressure)
        self._set(TAG.TAG_CORE_FLOW_VALUE,         flow)
        self._set(TAG.TAG_SG_IN_PRESSURE_VALUE,    sg_in_p)
        self._set(TAG.TAG_PRIMARY_RAD_MON_VALUE,   rad)

        self._set(TAG.TAG_SG_SEC_TEMP_IN_VALUE,    sg_sec_t_in)
        self._set(TAG.TAG_SG_SEC_TEMP_OUT_VALUE,   sg_sec_t_out)
        self._set(TAG.TAG_SG_STEAM_PRESSURE_VALUE, sg_p)
        self._set(TAG.TAG_SG_LEVEL_VALUE,          sg_level)
        self._set(TAG.TAG_SG_FEEDWATER_FLOW_VALUE, self._sg_fw_meas)
        self._set(TAG.TAG_SG_LEAK_MON_VALUE,       sg_leak)

        # =========================
        # Sensor logging → src/logs/logs-Factory.log
        # =========================
        self._loop_idx += 1
        if (self._loop_idx % self._log_every) == 0:
            data = {
                "ts": datetime.now().isoformat(timespec="milliseconds"),
                "flux": flux, "temp_in": temp_in, "temp_out": temp_out,
                "pressure": pressure, "flow": flow, "sg_in_p": sg_in_p, "rad": rad,
                "sg_sec_t_in": sg_sec_t_in, "sg_sec_t_out": sg_sec_t_out,
                "sg_p": sg_p, "sg_level": sg_level, "sg_fw_flow": self._sg_fw_meas,
                "sg_leak": sg_leak
            }
            if self._round_enabled:
                r = {
                    "ts": data["ts"],
                    "flux": round(data["flux"], 6),
                    "temp_in": round(data["temp_in"], 3),
                    "temp_out": round(data["temp_out"], 3),
                    "pressure": round(data["pressure"], 3),
                    "flow": round(data["flow"], 4),
                    "sg_in_p": round(data["sg_in_p"], 3),
                    "rad": round(data["rad"], 4),
                    "sg_sec_t_in": round(data["sg_sec_t_in"], 3),
                    "sg_sec_t_out": round(data["sg_sec_t_out"], 3),
                    "sg_p": round(data["sg_p"], 4),
                    "sg_level": round(data["sg_level"], 3),
                    "sg_fw_flow": round(data["sg_fw_flow"], 4),
                    "sg_leak": round(data["sg_leak"], 4),
                }
                txt = (
                    f"ts={r['ts']} "
                    f"flux={r['flux']} temp_in={r['temp_in']} temp_out={r['temp_out']} "
                    f"pressure={r['pressure']} flow={r['flow']} sg_in_p={r['sg_in_p']} rad={r['rad']} "
                    f"sg_sec_t_in={r['sg_sec_t_in']} sg_sec_t_out={r['sg_sec_t_out']} "
                    f"sg_p={r['sg_p']} sg_level={r['sg_level']} sg_fw_flow={r['sg_fw_flow']} sg_leak={r['sg_leak']} || "
                    f"{json.dumps(r, separators=(',', ':'))}"
                )
            else:
                txt = f"SENSORS || {json.dumps(data, separators=(',', ':'))}"

            self._sensor_logger.info(txt)

    def init(self):
        initial_list = [(tag, TAG.TAG_LIST[tag]['default']) for tag in TAG.TAG_LIST]
        self._connector.initialize(initial_list)

        self._cool_valve_eff = self._get(TAG.TAG_CORE_COOLANT_VALVE_CMD)
        self._loop_valve_eff = self._get(TAG.TAG_PRIMARY_LOOP_VALVE_CMD)

        self._sg_fw_meas = 0.02 + 0.98 * self._clamp01(self._get(TAG.TAG_SG_FEEDWATER_VALVE_CMD))

        self._rad_spike = {'active': False, 'until': datetime.now(), 'level': PHYSICS.RAD_BASELINE}
        self._sg_leak_spike = {'active': False, 'until': datetime.now(), 'level': 0.0}

    @staticmethod
    def recreate_connection():
        return True

    @staticmethod
    def _clamp(x, lo, hi):
        return lo if x < lo else hi if x > hi else x

    @staticmethod
    def _clamp01(x):
        return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


if __name__ == '__main__':
    factory = FactorySimulation()
    factory.start()
