import logging
import os

from ics_sim.Device import PLC, SensorConnector, ActuatorConnector
from Configs import TAG, Controllers, Connection


class PLC1(PLC):
    # ---- Core/primary thresholds ----
    HYST     = 0.5    # temp/flow alarm clear margin (°C / a.u.)
    P_HYST   = 0.05   # MPa hysteresis for core pressure controls
    RAD_HYST = 0.02   # µSv/h alarm clear margin

    # ---- Steam generator (secondary) hysteresis ----
    SG_P_HYST = 0.10  # MPa relief close hysteresis (secondary side)

    # Feedwater PI-ish gains (very light)
    FW_KP = 0.006
    FW_KI = 0.000004

    def __init__(self):
        sensor_connector = SensorConnector(Connection.CONNECTION)
        actuator_connector = ActuatorConnector(Connection.CONNECTION)
        super().__init__(1, sensor_connector, actuator_connector, TAG.TAG_LIST, Controllers.PLCs)

        # ----- File logging: append to src/logs/logs-plc1.log -----
        os.makedirs("src/logs", exist_ok=True)
        self._logger = logging.getLogger("PLC1_DECISIONS")
        self._logger.setLevel(logging.INFO)
        if not any(isinstance(h, logging.FileHandler) and getattr(h, "_plc1_handler", False)
                   for h in self._logger.handlers):
            fh = logging.FileHandler("src/logs/logs-plc1.log", mode="a", encoding="utf-8")
            fh._plc1_handler = True
            fh.setLevel(logging.INFO)
            fh.setFormatter(logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] PLC1: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            ))
            self._logger.addHandler(fh)

        # Integrator for feedwater valve in AUTO
        self._fw_int = 0.0

        # Trackers for transition logs
        self._prev_core_relief = None
        self._prev_sg_relief = None
        self._prev_alarm = None

    # ---------- small helpers ----------
    def _read_many(self, tags):
        """Read a dict of tag->value."""
        out = {}
        for t in tags:
            try:
                out[t] = self._get(t)
            except Exception as e:
                out[t] = f"ERR:{e}"
        return out

    def _write(self, tag, new_value, reason=""):
        """Write tag and log previous->new with reason."""
        try:
            old = self._get(tag)
        except Exception:
            old = "NA"
        self._set(tag, new_value)
        self._logger.info(f"WRITE {tag} {old} -> {new_value}  {('['+reason+']') if reason else ''}")

    def _logic(self):
        # -------- Read sensors (core / primary) --------
        core_reads = self._read_many([
            TAG.TAG_CORE_NEUTRON_FLUX_VALUE,
            TAG.TAG_CORE_TEMP_IN_VALUE,
            TAG.TAG_CORE_TEMP_OUT_VALUE,
            TAG.TAG_CORE_PRESSURE_VALUE,
            TAG.TAG_SG_IN_PRESSURE_VALUE,
            TAG.TAG_CORE_FLOW_VALUE,
            TAG.TAG_PRIMARY_RAD_MON_VALUE,
        ])

        flux   = core_reads[TAG.TAG_CORE_NEUTRON_FLUX_VALUE]
        t_in   = core_reads[TAG.TAG_CORE_TEMP_IN_VALUE]
        t_out  = core_reads[TAG.TAG_CORE_TEMP_OUT_VALUE]
        p_core = core_reads[TAG.TAG_CORE_PRESSURE_VALUE]
        p_sg_in= core_reads[TAG.TAG_SG_IN_PRESSURE_VALUE]
        flow   = core_reads[TAG.TAG_CORE_FLOW_VALUE]
        rad    = core_reads[TAG.TAG_PRIMARY_RAD_MON_VALUE]

        # -------- Read sensors (steam generator / secondary) --------
        sg_reads = self._read_many([
            TAG.TAG_SG_SEC_TEMP_IN_VALUE,
            TAG.TAG_SG_SEC_TEMP_OUT_VALUE,
            TAG.TAG_SG_STEAM_PRESSURE_VALUE,
            TAG.TAG_SG_LEVEL_VALUE,
            TAG.TAG_SG_FEEDWATER_FLOW_VALUE,
        ])
        sg_t_in   = sg_reads[TAG.TAG_SG_SEC_TEMP_IN_VALUE]
        sg_t_out  = sg_reads[TAG.TAG_SG_SEC_TEMP_OUT_VALUE]
        sg_p      = sg_reads[TAG.TAG_SG_STEAM_PRESSURE_VALUE]
        sg_level  = sg_reads[TAG.TAG_SG_LEVEL_VALUE]
        sg_fwflow = sg_reads[TAG.TAG_SG_FEEDWATER_FLOW_VALUE]

        # -------- Read SPs / limits (core/primary) --------
        sp_primary = self._read_many([
            TAG.TAG_CORE_NEUTRON_FLUX_SP,
            TAG.TAG_CORE_TEMP_OUT_MAX,
            TAG.TAG_CORE_PRESSURE_MAX,
            TAG.TAG_CORE_PRESSURE_HIHI,
            TAG.TAG_CORE_FLOW_MIN,
            TAG.TAG_PRIMARY_RAD_ALARM_MAX,
        ])
        flux_sp = sp_primary[TAG.TAG_CORE_NEUTRON_FLUX_SP]
        tmax    = sp_primary[TAG.TAG_CORE_TEMP_OUT_MAX]
        pmax    = sp_primary[TAG.TAG_CORE_PRESSURE_MAX]
        phihi   = sp_primary[TAG.TAG_CORE_PRESSURE_HIHI]
        fmin    = sp_primary[TAG.TAG_CORE_FLOW_MIN]
        radmax  = sp_primary[TAG.TAG_PRIMARY_RAD_ALARM_MAX]

        # -------- Read limits (steam generator / secondary) --------
        sp_sg = self._read_many([
            TAG.TAG_SG_LEVEL_MIN, TAG.TAG_SG_LEVEL_MAX,
            TAG.TAG_SG_STEAM_P_MAX, TAG.TAG_SG_STEAM_P_HIHI
        ])
        sg_lvl_min = sp_sg[TAG.TAG_SG_LEVEL_MIN]
        sg_lvl_max = sp_sg[TAG.TAG_SG_LEVEL_MAX]
        sg_p_max   = sp_sg[TAG.TAG_SG_STEAM_P_MAX]
        sg_p_hihi  = sp_sg[TAG.TAG_SG_STEAM_P_HIHI]

        # Log a compact snapshot of readings & limits each scan
        self._logger.info(
            "READS core: flux=%.3f Tin=%.3f Tout=%.3f P=%.3f PsgIn=%.3f Flow=%.3f Rad=%.3f | "
            "sg: Tin=%.3f Tout=%.3f P=%.3f Lvl=%.3f Fw=%.3f | "
            "LIMS: TMax=%.3f PMax=%.3f PHiHi=%.3f Fmin=%.3f RadMax=%.3f | "
            "SG: Lmin=%.3f Lmax=%.3f Pmax=%.3f PHiHi=%.3f" %
            (flux, t_in, t_out, p_core, p_sg_in, flow, rad,
             sg_t_in, sg_t_out, sg_p, sg_level, sg_fwflow,
             tmax, pmax, phihi, fmin, radmax,
             sg_lvl_min, sg_lvl_max, sg_p_max, sg_p_hihi)
        )

        # ===========================
        # 1) Control rods (reactivity)
        # ===========================
        if not self._check_manual_input(TAG.TAG_CORE_CONTROL_ROD_MODE, TAG.TAG_CORE_CONTROL_ROD_POS_VALUE):
            rod = self._get(TAG.TAG_CORE_CONTROL_ROD_POS_VALUE)
            err = flux - flux_sp
            new_rod = min(max(rod + err * 4.0, 0.0), 100.0)
            if new_rod != rod:
                self._write(TAG.TAG_CORE_CONTROL_ROD_POS_VALUE, new_rod, reason=f"Reactivity: flux_err={err:.3f}")

        # ===========================
        # 2) Primary pump speed (flow)
        # ===========================
        if not self._check_manual_input(TAG.TAG_CORE_RCP_MODE, TAG.TAG_CORE_RCP_SPEED_CMD):
            cmd = self._get(TAG.TAG_CORE_RCP_SPEED_CMD)
            old_cmd = cmd
            if t_out > (tmax - 3.0) or flow < (fmin + 0.05):
                cmd += 0.02
            elif t_out < (tmax - 8.0) and flow > (fmin + 0.2):
                cmd -= 0.01
            cmd = min(max(cmd, 0.0), 1.0)
            if cmd != old_cmd:
                self._write(TAG.TAG_CORE_RCP_SPEED_CMD, cmd,
                            reason=f"RCP adjust: Tout={t_out:.3f}, Flow={flow:.3f}")

        # ===========================
        # 3) Heat removal valve (primary-side HX path)
        # ===========================
        if not self._check_manual_input(TAG.TAG_CORE_COOLANT_VALVE_MODE, TAG.TAG_CORE_COOLANT_VALVE_CMD):
            v = self._get(TAG.TAG_CORE_COOLANT_VALVE_CMD)
            old_v = v
            if t_out > (tmax - 2.0):
                v += 0.02
            elif t_out < (tmax - 10.0):
                v -= 0.01
            v = min(max(v, 0.0), 1.0)
            if v != old_v:
                self._write(TAG.TAG_CORE_COOLANT_VALVE_CMD, v, reason=f"HX valve: Tout={t_out:.3f}")

        # ===========================
        # 4) Primary loop flow-control valve
        # ===========================
        if not self._check_manual_input(TAG.TAG_PRIMARY_LOOP_VALVE_MODE, TAG.TAG_PRIMARY_LOOP_VALVE_CMD):
            lv = self._get(TAG.TAG_PRIMARY_LOOP_VALVE_CMD)
            old_lv = lv
            if flow < (fmin + 0.05) or t_out > (tmax - 5.0):
                lv += 0.02
            elif flow > (fmin + 0.2) and t_out < (tmax - 12.0):
                lv -= 0.01
            lv = min(max(lv, 0.0), 1.0)
            if lv != old_lv:
                self._write(TAG.TAG_PRIMARY_LOOP_VALVE_CMD, lv,
                            reason=f"Loop valve: Flow={flow:.3f}, Tout={t_out:.3f}")

        # ===========================
        # 5) Pressurizer: heater & spray (core pressure control)
        # ===========================
        if not self._check_manual_input(TAG.TAG_CORE_PRESSURIZER_HEATER_MODE, TAG.TAG_CORE_PRESSURIZER_HEATER_CMD):
            h = self._get(TAG.TAG_CORE_PRESSURIZER_HEATER_CMD)
            old_h = h
            if p_core < (pmax - self.P_HYST):
                h += 0.03
            elif p_core > (pmax + 0.02):
                h -= 0.02
            h = min(max(h, 0.0), 1.0)
            if h != old_h:
                self._write(TAG.TAG_CORE_PRESSURIZER_HEATER_CMD, h,
                            reason=f"Pressurizer heater: Pcore={p_core:.3f}")

        if not self._check_manual_input(TAG.TAG_CORE_PRESSURIZER_SPRAY_MODE, TAG.TAG_CORE_PRESSURIZER_SPRAY_CMD):
            s = self._get(TAG.TAG_CORE_PRESSURIZER_SPRAY_CMD)
            old_s = s
            if p_core > (pmax + 0.03):
                s += 0.03
            elif p_core < (pmax - self.P_HYST):
                s -= 0.02
            s = min(max(s, 0.0), 1.0)
            if s != old_s:
                self._write(TAG.TAG_CORE_PRESSURIZER_SPRAY_CMD, s,
                            reason=f"Pressurizer spray: Pcore={p_core:.3f}")

        # Relief (auto) for core/primary pressure
        relief_open = self._get(TAG.TAG_CORE_RELIEF_VALVE_STATUS)
        new_relief = relief_open
        if p_core > phihi:
            new_relief = 1
        elif p_core < (pmax - 0.05):
            new_relief = 0
        if new_relief != relief_open:
            self._write(TAG.TAG_CORE_RELIEF_VALVE_STATUS, new_relief,
                        reason=f"Core relief {'OPEN' if new_relief else 'CLOSE'}: Pcore={p_core:.3f}")
        # Track analog command mirroring relief (if in AUTO)
        if not self._check_manual_input(TAG.TAG_CORE_PRESSURIZER_VALVE_MODE, TAG.TAG_CORE_PRESSURIZER_VALVE_CMD):
            pv = 1.0 if new_relief else 0.0
            self._write(TAG.TAG_CORE_PRESSURIZER_VALVE_CMD, pv,
                        reason="Mirror relief to analog cmd")

        # Remember transition for summary logs
        if self._prev_core_relief is None or self._prev_core_relief != new_relief:
            self._logger.info(f"Core relief state -> {new_relief}")
            self._prev_core_relief = new_relief

        # ======================================
        # 6) Steam generator: Feedwater control (hold level near mid of min/max)
        # ======================================
        if not self._check_manual_input(TAG.TAG_SG_FEEDWATER_VALVE_MODE, TAG.TAG_SG_FEEDWATER_VALVE_CMD):
            fw_cmd = self._get(TAG.TAG_SG_FEEDWATER_VALVE_CMD)
            old_fw = fw_cmd
            lvl_sp_mid = (sg_lvl_max + sg_lvl_min) / 2.0
            lvl_err = (lvl_sp_mid - sg_level)  # positive -> increase feedwater
            self._fw_int += lvl_err * 0.001  # slow integral
            self._fw_int = min(max(self._fw_int, -0.5), 0.5)

            fw_cmd = min(max(fw_cmd + (self.FW_KP * lvl_err) + (self.FW_KI * self._fw_int), 0.0), 1.0)
            if fw_cmd != old_fw:
                self._write(TAG.TAG_SG_FEEDWATER_VALVE_CMD, fw_cmd,
                            reason=f"FW valve: Lvl={sg_level:.2f} SPmid={lvl_sp_mid:.2f} err={lvl_err:.2f}")
        else:
            # If operator is in manual, keep integrator from winding up
            self._fw_int *= 0.98

        # ======================================================
        # 7) Steam generator: Steam/relief valve (pressure control)
        # ======================================================
        sg_relief = self._get(TAG.TAG_SG_RELIEF_VALVE_STATUS)
        new_sg_relief = sg_relief
        if sg_p > sg_p_hihi:
            new_sg_relief = 1
        elif sg_p < (sg_p_max - self.SG_P_HYST):
            new_sg_relief = 0
        if new_sg_relief != sg_relief:
            self._write(TAG.TAG_SG_RELIEF_VALVE_STATUS, new_sg_relief,
                        reason=f"SG steam relief {'OPEN' if new_sg_relief else 'CLOSE'}: P={sg_p:.3f}")
        if self._prev_sg_relief is None or self._prev_sg_relief != new_sg_relief:
            self._logger.info(f"SG relief state -> {new_sg_relief}")
            self._prev_sg_relief = new_sg_relief

        # ===========================
        # 8) Alarm logic (latched)
        # ===========================
        alarm = self._get(TAG.TAG_CORE_ALARM_STATUS)

        # Core trips
        core_trip = (t_out > tmax) or (p_core > pmax) or (flow < fmin) or (rad > radmax)
        # SG trips (secondary)
        sg_trip = (sg_p > sg_p_max) or (sg_level < sg_lvl_min) or (sg_level > sg_lvl_max)

        trip = core_trip or sg_trip

        if alarm:
            clear_core = (t_out < (tmax - self.HYST)) \
                         and (p_core < (pmax - self.P_HYST)) \
                         and (flow > (fmin + 0.02)) \
                         and (rad < (radmax - self.RAD_HYST))

            clear_sg = (sg_p < (sg_p_max - self.SG_P_HYST)) \
                       and (sg_lvl_min + 2.0) < sg_level < (sg_lvl_max - 2.0)

            if clear_core and clear_sg:
                self._write(TAG.TAG_CORE_ALARM_STATUS, 0, reason="Alarm clear conditions satisfied")
        else:
            if trip:
                self._write(TAG.TAG_CORE_ALARM_STATUS, 1,
                            reason=f"Alarm trip: core_trip={core_trip} sg_trip={sg_trip}")

        # Alarm transition summary
        now_alarm = self._get(TAG.TAG_CORE_ALARM_STATUS)
        if self._prev_alarm is None or now_alarm != self._prev_alarm:
            self._logger.warning(f"ALARM {'SET' if now_alarm else 'CLEARED'} "
                                 f"(core_trip={core_trip}, sg_trip={sg_trip})")
            self._prev_alarm = now_alarm

    def _post_logic_update(self):
        super()._post_logic_update()
        # CSV snapshots can be enabled via set_record_variables(True)


if __name__ == '__main__':
    plc1 = PLC1()
    plc1.set_record_variables(True)
    plc1.start()
