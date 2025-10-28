import logging
import os
from datetime import datetime

from ics_sim.Device import HMI
from Configs import TAG, Controllers


class HMI1(HMI):
    def __init__(self):
        super().__init__('HMI1', TAG.TAG_LIST, Controllers.PLCs, 500)

        self.title_length = 36
        self.msg1_length = 22
        self.msg2_length = 12

        self._border_top = "┌" + "─"*self.title_length + "┬" + "─"*self.msg1_length + "┬" + "─"*self.msg2_length + "┐"
        self._border_mid = "├" + "─"*self.title_length + "┼" + "─"*self.msg1_length + "┼" + "─"*self.msg2_length + "┤"
        self._border_bot = "└" + "─"*self.title_length + "┴" + "─"*self.msg1_length + "┴" + "─"*self.msg2_length + "┘"

        # ---------------------------------------------------------
        # PART 1: Fuel & Primary Heat Removal (core)
        # PART 2: Primary-loop Instrumentation (only)
        # PART 3: Heat transfer in the Steam Generator (secondary)
        # ---------------------------------------------------------
        self._ordered_rows = [
            # ===== Part 1 =====
            "__SECTION__1) FUEL & PRIMARY HEAT REMOVAL",

            # Reactivity (tightly coupled: flux + rods)
            "__SECTION__— Reactivity —",
            "core_neutron_flux",
            "core_neutron_flux_sp",
            "core_control_rod_pos",
            "core_control_rod_mode",

            # Coolant & Flow (leaves/enters core, plus loop controls)
            "__SECTION__— Coolant & Flow —",
            "core_temp_in",
            "core_temp_out",
            "core_temp_out_max",
            "core_coolant_valve_cmd",
            "core_coolant_valve_mode",
            "core_rcp_speed_cmd",
            "core_rcp_mode",
            "core_flow",
            "core_flow_min",

            # Pressure & Pressurizer (keep water subcooled, no boiling)
            "__SECTION__— Pressure & Pressurizer —",
            "core_pressure",
            "core_pressure_max",
            "core_pressure_hihi",
            "core_pressurizer_heater_cmd",
            "core_pressurizer_heater_mode",
            "core_pressurizer_spray_cmd",
            "core_pressurizer_spray_mode",
            "core_pressurizer_valve_cmd",
            "core_pressurizer_valve_mode",
            "core_relief_valve_status",

            # ===== Part 2 =====
            "__SECTION__2) PRIMARY-LOOP INSTRUMENTATION",
            "sg_in_pressure",
            "primary_loop_valve_cmd",
            "primary_loop_valve_mode",
            "primary_loop_valve_pos",
            "primary_rad_mon",
            "primary_rad_alarm_max",

            # ===== Part 3 =====
            "__SECTION__3) HEAT TRANSFER IN THE STEAM GENERATOR",
            "sg_sec_temp_in",
            "sg_sec_temp_out",
            "sg_steam_pressure",
            "sg_level",
            "sg_feedwater_flow",
            "sg_feedwater_valve_cmd",
            "sg_feedwater_valve_mode",
            "sg_relief_valve_status",

            # Overall plant status
            "__SECTION__STATUS",
            "core_alarm_status",
        ]

        # Pretty labels for left column
        self._pretty = {
            # Part 1 — Reactivity
            "core_neutron_flux":              "Neutron Flux",
            "core_neutron_flux_sp":           "Flux Setpoint",
            "core_control_rod_pos":           "Control Rod Position",
            "core_control_rod_mode":          "Control Rod Mode",

            # Part 1 — Coolant & Flow
            "core_temp_in":                   "Coolant Temp (In)",
            "core_temp_out":                  "Coolant Temp (Out)",
            "core_temp_out_max":              "Max Outlet Temp",
            "core_coolant_valve_cmd":         "Coolant Valve Command",
            "core_coolant_valve_mode":        "Coolant Valve Mode",
            "core_rcp_speed_cmd":             "RCP Speed Command",
            "core_rcp_mode":                  "RCP Mode",
            "core_flow":                      "Coolant Flow",
            "core_flow_min":                  "Min Flow",

            # Part 1 — Pressure & Pressurizer
            "core_pressure":                  "Primary Pressure",
            "core_pressure_max":              "Max Pressure",
            "core_pressure_hihi":             "HI-HI Pressure",
            "core_pressurizer_heater_cmd":    "Pressurizer Heater Cmd",
            "core_pressurizer_heater_mode":   "Pressurizer Heater Mode",
            "core_pressurizer_spray_cmd":     "Pressurizer Spray Cmd",
            "core_pressurizer_spray_mode":    "Pressurizer Spray Mode",
            "core_pressurizer_valve_cmd":     "Pressurizer Relief Cmd",
            "core_pressurizer_valve_mode":    "Pressurizer Relief Mode",
            "core_relief_valve_status":       "Relief Valve Status",

            # Part 2 — Primary-loop instrumentation
            "sg_in_pressure":                 "SG Inlet Pressure",
            "primary_loop_valve_cmd":         "Primary Loop Valve Cmd",
            "primary_loop_valve_mode":        "Primary Loop Valve Mode",
            "primary_loop_valve_pos":         "Primary Loop Valve Pos",
            "primary_rad_mon":                "Primary Piping Radiation",
            "primary_rad_alarm_max":          "Radiation Alarm Max",

            # Part 3 — Steam generator (secondary)
            "sg_sec_temp_in":                 "SG Sec Temp (In)",
            "sg_sec_temp_out":                "SG Sec Temp (Out)",
            "sg_steam_pressure":              "Steam Pressure",
            "sg_level":                       "SG Level",
            "sg_feedwater_flow":              "Feedwater Flow",
            "sg_feedwater_valve_cmd":         "Feedwater Valve Cmd",
            "sg_feedwater_valve_mode":        "Feedwater Valve Mode",
            "sg_relief_valve_status":         "Steam Relief Status",

            # Status
            "core_alarm_status":              "Core Alarm",
        }

        # Build rows (section headers always; data rows only if base key exists)
        self._available_keys = set(tag.rsplit('_', 1)[0] for tag in self.tags)
        self._rows = []
        for key in self._ordered_rows:
            if key.startswith("__SECTION__"):
                title = key.replace("__SECTION__", "").strip()
                self._rows.append({"type": "section", "label": title})
            else:
                if key in self._available_keys:
                    label = self._pretty.get(key, key.replace("_", " ").title())
                    self._rows.append({
                        "type": "data",
                        "key": key,
                        "tag": label.center(self.title_length, " "),
                        "msg1": "",
                        "msg2": ""
                    })

        self._latency = 0

        # ---------- one-line file logger ----------
        os.makedirs("src/logs", exist_ok=True)
        self._logger = logging.getLogger("HMI1_SNAPSHOTS")
        self._logger.setLevel(logging.INFO)
        if not any(isinstance(h, logging.FileHandler) and getattr(h, "_hmi1_handler", False)
                   for h in self._logger.handlers):
            fh = logging.FileHandler("src/logs/logs-HMI1.log", mode="a", encoding="utf-8")
            fh._hmi1_handler = True
            fh.setLevel(logging.INFO)
            fh.setFormatter(logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] HMI1: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            ))
            self._logger.addHandler(fh)

    def _display(self):
        # draw box to console
        self.__show_table()
        # and also write a compact one-line snapshot to file
        self.__log_one_line_snapshot()

    def _operate(self):
        self.__update_messages()

    def __update_messages(self):
        self._latency = 0

        # Clear cells
        for row in self._rows:
            if row["type"] == "data":
                row["msg1"] = ""
                row["msg2"] = ""

        # Fill cells from live tags
        for tag_name in self.tags:
            key, suffix = tag_name.rsplit('_', 1)
            for row in self._rows:
                if row["type"] != "data" or row.get("key") != key:
                    continue
                if suffix in ("value", "status"):
                    row["msg2"] += self.__get_formatted_value(tag_name)
                else:
                    row["msg1"] += self.__get_formatted_value(tag_name)

        # Pad empties
        for row in self._rows:
            if row["type"] != "data":
                continue
            if not row["msg1"]:
                row["msg1"] = "".center(self.msg1_length, " ")
            if not row["msg2"]:
                row["msg2"] = "".center(self.msg2_length, " ")

    def __get_val(self, tag, default="NULL"):
        try:
            return self._receive(tag)
        except Exception:
            return default

    def __log_one_line_snapshot(self):
        # Grab key points across Parts 1–3
        flux   = self.__get_val(TAG.TAG_CORE_NEUTRON_FLUX_VALUE)
        fluxsp = self.__get_val(TAG.TAG_CORE_NEUTRON_FLUX_SP)
        t_in   = self.__get_val(TAG.TAG_CORE_TEMP_IN_VALUE)
        t_out  = self.__get_val(TAG.TAG_CORE_TEMP_OUT_VALUE)
        p_core = self.__get_val(TAG.TAG_CORE_PRESSURE_VALUE)
        flow   = self.__get_val(TAG.TAG_CORE_FLOW_VALUE)

        p_sgin = self.__get_val(TAG.TAG_SG_IN_PRESSURE_VALUE)
        rad    = self.__get_val(TAG.TAG_PRIMARY_RAD_MON_VALUE)
        lv_pos = self.__get_val(TAG.TAG_PRIMARY_LOOP_VALVE_POS_VALUE)

        sg_tin  = self.__get_val(TAG.TAG_SG_SEC_TEMP_IN_VALUE)
        sg_tout = self.__get_val(TAG.TAG_SG_SEC_TEMP_OUT_VALUE)
        sg_p    = self.__get_val(TAG.TAG_SG_STEAM_PRESSURE_VALUE)
        sg_lvl  = self.__get_val(TAG.TAG_SG_LEVEL_VALUE)
        sg_fw   = self.__get_val(TAG.TAG_SG_FEEDWATER_FLOW_VALUE)

        fw_cmd  = self.__get_val(TAG.TAG_SG_FEEDWATER_VALVE_CMD)
        fw_mode = self.__get_val(TAG.TAG_SG_FEEDWATER_VALVE_MODE)
        sg_rel  = self.__get_val(TAG.TAG_SG_RELIEF_VALVE_STATUS)

        alarm   = self.__get_val(TAG.TAG_CORE_ALARM_STATUS)

        # Build a compact, single-line message
        line = (
            f"P1 flux={self.__fmt(flux)} sp={self.__fmt(fluxsp)} "
            f"Tin={self.__fmt(t_in)} Tout={self.__fmt(t_out)} "
            f"Pcore={self.__fmt(p_core)} Flow={self.__fmt(flow)} | "
            f"P2 PsgIn={self.__fmt(p_sgin)} Rad={self.__fmt(rad)} "
            f"LoopPos={self.__fmt(lv_pos)} | "
            f"P3 SG_Tin={self.__fmt(sg_tin)} SG_Tout={self.__fmt(sg_tout)} "
            f"SG_P={self.__fmt(sg_p)} SG_Lvl={self.__fmt(sg_lvl)} "
            f"FW_Flow={self.__fmt(sg_fw)} FW_Cmd={self.__fmt(fw_cmd)} "
            f"FW_Mode={self.__fmt_mode(fw_mode)} SG_Relief={int(bool(sg_rel))} | "
            f"ALARM={int(bool(alarm))}"
        )
        self._logger.info(line)

    def __fmt(self, v):
        try:
            return f"{float(v):.3f}"
        except Exception:
            return str(v)

    def __fmt_mode(self, v):
        try:
            v = int(v)
        except Exception:
            return str(v)
        return {1: "Off", 2: "On", 3: "Auto"}.get(v, str(v))

    def __get_formatted_value(self, tag):
        timestamp = datetime.now()
        suffix = tag.rsplit('_', 1)[1]

        try:
            value = self._receive(tag)
            err = None
        except Exception as e:
            self.report(e.__str__(), logging.WARNING)
            value = "NULL"
            err = e

        if suffix == "mode":
            if value == 1:
                value = self._make_text("Off man".center(self.msg1_length, " "), self.COLOR_YELLOW)
            elif value == 2:
                value = self._make_text("On man".center(self.msg1_length, " "), self.COLOR_YELLOW)
            elif value == 3:
                value = self._make_text("Auto".center(self.msg1_length, " "), self.COLOR_GREEN)
            else:
                value = self._make_text(str(value).center(self.msg1_length, " "), self.COLOR_RED)

        elif suffix == "status":
            if value == "NULL":
                value = self._make_text(str(value).center(self.msg2_length, " "), self.COLOR_RED)
            elif value:
                value = self._make_text("ALM".center(self.msg2_length, " "), self.COLOR_RED)
            else:
                value = self._make_text("OK".center(self.msg2_length, " "), self.COLOR_GREEN)

        else:
            # numeric / setpoint / command / limits
            try:
                shown = round(float(value), 3)
            except Exception:
                shown = value
            value = self._make_text(str(shown).center(self.msg2_length, " "), self.COLOR_CYAN)

        elapsed = datetime.now() - timestamp
        if elapsed.microseconds > self._latency:
            self._latency = elapsed.microseconds
        return value

    def __show_table(self):
        result = " (Latency {}ms)\n".format(self._latency / 1000)
        first_row_drawn = False

        for row in self._rows:
            if row["type"] == "section":
                border = self._border_top if not first_row_drawn else self._border_mid
                result += border + "\n"
                title = f"— {row['label']} —".center(self.title_length, " ")
                result += f"│{title}│{'':{self.msg1_length}}│{'':{self.msg2_length}}│\n"
                first_row_drawn = True
                continue

            border = self._border_top if not first_row_drawn else self._border_mid
            result += border + "\n"
            first_row_drawn = True
            result += '│{}│{}│{}│\n'.format(row["tag"], row["msg1"], row["msg2"])

        result += self._border_bot + "\n"
        # Keep the human-readable box only on console
        self.report(result)


if __name__ == '__main__':
    hmi1 = HMI1()
    hmi1.start()
