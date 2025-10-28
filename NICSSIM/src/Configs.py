class SimulationConfig:
    # Constants
    EXECUTION_MODE_LOCAL = 'local'
    EXECUTION_MODE_DOCKER = 'docker'
    EXECUTION_MODE_GNS3 = 'gns3'

    # configurable
    EXECUTION_MODE = EXECUTION_MODE_DOCKER


class PHYSICS:
    """
    Minimal thermal-hydraulic coefficients for the toy core/primary loop model
    plus a simple steam-generator (secondary loop) model.
    Tuned for stable, readable dynamics at ~100 ms scan.
    """
    # --- Core / primary thermal terms ---
    AMBIENT_TEMP = 290.0          # °C (loop inlet baseline)
    HEAT_GAIN_K = 8.0e-3          # °C/ms per unit neutron flux
    COOLING_K = 4.0e-3            # °C/ms per (flow * valve) * temp_delta

    # --- Primary pressure model ---
    PRESSURE_K_TEMP   = 0.035     # MPa per (TempOut - AMBIENT_TEMP)
    PRESSURE_K_HEATER = 0.020     # MPa/s at 100% heater (scaled by dt)
    PRESSURE_K_SPRAY  = 0.030     # MPa/s reduction at 100% spray (scaled by dt)
    PRESSURE_K_RELIEF = 0.080     # MPa/s reduction when relief is open (scaled by dt)

    # --- Actuator/sensor inertias (how fast actuals approach commands) ---
    FLOW_INERTIA  = 0.003         # 1/ms -> approach commanded pump speed
    VALVE_INERTIA = 0.003         # 1/ms -> approach commanded valve opening
    FLUX_INERTIA  = 0.002         # 1/ms -> approach reactivity/flux target

    # --- Leak/radiation stub (primary loop piping) ---
    RAD_BASELINE   = 0.02         # µSv/h baseline on primary piping
    RAD_SPIKE_MAX  = 0.50         # µSv/h peak during a rare transient
    RAD_SPIKE_PROB = 0.0005       # chance per scan to start a small spike
    RAD_SPIKE_SEC  = (3, 12)      # duration seconds (min, max)

    # --- Steam generator (secondary loop) ---
    SG_SEC_FEEDWATER_TEMP = 220.0   # °C cold/return water entering SG (toy)
    SG_HX_K = 5.0e-3                # °C/ms heat transfer coefficient primary->secondary
    SG_LEVEL_INERTIA = 0.002        # 1/ms level response to feedwater/boil-off
    SG_FEEDWATER_FLOW_MAX = 1.0     # a.u., normalized
    SG_BOIL_OFF_K = 0.004           # level reduction per unit steam production
    SG_PRESSURE_K = 0.020           # MPa/s per unit steam production (scaled by dt)
    SG_PRESSURE_RELIEF_K = 0.08     # MPa/s reduction when relief open (scaled by dt)


class TAG:
    """
    Core + primary loop + steam generator (secondary loop) tags.
    - Inputs (type='input') are sensor readings from the plant.
    - Outputs (type='output') are setpoints, modes, and actuator commands.
    All signals live on PLC1 for now.
    """

    # --- Sensor values (inputs) ---
    TAG_CORE_NEUTRON_FLUX_VALUE    = 'core_neutron_flux_value'      # a.u.
    TAG_CORE_TEMP_IN_VALUE         = 'core_temp_in_value'           # °C
    TAG_CORE_TEMP_OUT_VALUE        = 'core_temp_out_value'          # °C
    TAG_CORE_PRESSURE_VALUE        = 'core_pressure_value'          # MPa (pressurizer/primary)
    TAG_CORE_FLOW_VALUE            = 'core_flow_value'              # a.u. (0..1)

    # Extra primary-loop instrumentation
    TAG_SG_IN_PRESSURE_VALUE       = 'sg_in_pressure_value'         # MPa (at SG inlet)
    TAG_PRIMARY_RAD_MON_VALUE      = 'primary_rad_mon_value'        # µSv/h along piping
    TAG_PRIMARY_LOOP_VALVE_POS_VALUE = 'primary_loop_valve_pos_value'  # 0..1 (measured position)

    # --- Actuator actuals / commands / modes (outputs) ---
    TAG_CORE_CONTROL_ROD_POS_VALUE = 'core_control_rod_pos_value'   # 0..100 %
    TAG_CORE_CONTROL_ROD_MODE      = 'core_control_rod_mode'        # 1=Off, 2=On, 3=Auto
    TAG_CORE_NEUTRON_FLUX_SP       = 'core_neutron_flux_sp'         # a.u.

    TAG_CORE_RCP_SPEED_CMD         = 'core_rcp_speed_cmd'           # 0..1
    TAG_CORE_RCP_MODE              = 'core_rcp_mode'                # 1=Off, 2=On, 3=Auto

    TAG_CORE_COOLANT_VALVE_CMD     = 'core_coolant_valve_cmd'       # 0..1 (heat removal path valve)
    TAG_CORE_COOLANT_VALVE_MODE    = 'core_coolant_valve_mode'      # 1=Off, 2=On, 3=Auto

    # Primary loop flow-control valve (separate from coolant heat removal valve)
    TAG_PRIMARY_LOOP_VALVE_CMD     = 'primary_loop_valve_cmd'       # 0..1
    TAG_PRIMARY_LOOP_VALVE_MODE    = 'primary_loop_valve_mode'      # 1=Off, 2=On, 3=Auto

    # Pressurizer controls
    TAG_CORE_PRESSURIZER_HEATER_CMD = 'core_pressurizer_heater_cmd' # 0..1
    TAG_CORE_PRESSURIZER_HEATER_MODE= 'core_pressurizer_heater_mode'# 1=Off, 2=On, 3=Auto
    TAG_CORE_PRESSURIZER_SPRAY_CMD  = 'core_pressurizer_spray_cmd'  # 0..1
    TAG_CORE_PRESSURIZER_SPRAY_MODE = 'core_pressurizer_spray_mode' # 1=Off, 2=On, 3=Auto
    TAG_CORE_PRESSURIZER_VALVE_CMD  = 'core_pressurizer_valve_cmd'  # 0..1 (relief analog; PLC sets auto)
    TAG_CORE_PRESSURIZER_VALVE_MODE = 'core_pressurizer_valve_mode' # 1=Off, 2=On, 3=Auto
    TAG_CORE_RELIEF_VALVE_STATUS    = 'core_relief_valve_status'    # 0/1 (auto, opens at HIHI)

    # --- Limits & alarms (outputs) ---
    TAG_CORE_TEMP_OUT_MAX          = 'core_temp_out_max'            # °C
    TAG_CORE_PRESSURE_MAX          = 'core_pressure_max'            # MPa (normal high)
    TAG_CORE_PRESSURE_HIHI         = 'core_pressure_hihi'           # MPa (relief setpoint)
    TAG_CORE_FLOW_MIN              = 'core_flow_min'                # a.u.
    TAG_PRIMARY_RAD_ALARM_MAX      = 'primary_rad_alarm_max'        # µSv/h
    TAG_CORE_ALARM_STATUS          = 'core_alarm_status'            # 0/1 (latched)

    # -------------------------------
    # Steam Generator (Secondary Loop)
    # -------------------------------
    # Sensors (inputs)
    TAG_SG_SEC_TEMP_IN_VALUE       = 'sg_sec_temp_in_value'         # °C (feedwater inlet to SG)
    TAG_SG_SEC_TEMP_OUT_VALUE      = 'sg_sec_temp_out_value'        # °C (steam/saturation temp)
    TAG_SG_STEAM_PRESSURE_VALUE    = 'sg_steam_pressure_value'      # MPa (steam space)
    TAG_SG_LEVEL_VALUE             = 'sg_level_value'               # % (0..100) normalized drum/SG level
    TAG_SG_FEEDWATER_FLOW_VALUE    = 'sg_feedwater_flow_value'      # a.u. (0..1)
    TAG_SG_LEAK_MON_VALUE          = 'sg_leak_mon_value'            # µSv/h (cross-contamination monitor)

    # Actuators / modes (outputs)
    TAG_SG_FEEDWATER_VALVE_CMD     = 'sg_feedwater_valve_cmd'       # 0..1
    TAG_SG_FEEDWATER_VALVE_MODE    = 'sg_feedwater_valve_mode'      # 1=Off, 2=On, 3=Auto
    TAG_SG_RELIEF_VALVE_STATUS     = 'sg_relief_valve_status'       # 0/1 (safety steam relief)

    # Limits (secondary)
    TAG_SG_LEVEL_MIN               = 'sg_level_min'                 # %
    TAG_SG_LEVEL_MAX               = 'sg_level_max'                 # %
    TAG_SG_STEAM_P_MAX             = 'sg_steam_p_max'               # MPa (normal high)
    TAG_SG_STEAM_P_HIHI            = 'sg_steam_p_hihi'              # MPa (safety relief)

    TAG_LIST = {
        # Inputs
        TAG_CORE_NEUTRON_FLUX_VALUE:       {'id': 0,  'plc': 1, 'type': 'input',  'fault': 0.0, 'default': 0.8},
        TAG_CORE_TEMP_IN_VALUE:            {'id': 1,  'plc': 1, 'type': 'input',  'fault': 0.0, 'default': 290.0},
        TAG_CORE_TEMP_OUT_VALUE:           {'id': 2,  'plc': 1, 'type': 'input',  'fault': 0.0, 'default': 300.0},
        TAG_CORE_PRESSURE_VALUE:           {'id': 3,  'plc': 1, 'type': 'input',  'fault': 0.0, 'default': 15.0},
        TAG_CORE_FLOW_VALUE:               {'id': 4,  'plc': 1, 'type': 'input',  'fault': 0.0, 'default': 0.6},
        TAG_SG_IN_PRESSURE_VALUE:          {'id': 5,  'plc': 1, 'type': 'input',  'fault': 0.0, 'default': 14.9},
        TAG_PRIMARY_RAD_MON_VALUE:         {'id': 6,  'plc': 1, 'type': 'input',  'fault': 0.0, 'default': 0.02},
        TAG_PRIMARY_LOOP_VALVE_POS_VALUE:  {'id': 7,  'plc': 1, 'type': 'input',  'fault': 0.0, 'default': 0.5},

        # Actuators / SPs / Modes
        TAG_CORE_CONTROL_ROD_POS_VALUE:    {'id': 8,  'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 50.0},
        TAG_CORE_CONTROL_ROD_MODE:         {'id': 9,  'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 3},
        TAG_CORE_NEUTRON_FLUX_SP:          {'id': 10, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 0.9},

        TAG_CORE_RCP_SPEED_CMD:            {'id': 11, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 0.6},
        TAG_CORE_RCP_MODE:                 {'id': 12, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 3},

        TAG_CORE_COOLANT_VALVE_CMD:        {'id': 13, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 0.5},
        TAG_CORE_COOLANT_VALVE_MODE:       {'id': 14, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 3},

        TAG_PRIMARY_LOOP_VALVE_CMD:        {'id': 15, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 0.5},
        TAG_PRIMARY_LOOP_VALVE_MODE:       {'id': 16, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 3},

        TAG_CORE_PRESSURIZER_HEATER_CMD:   {'id': 17, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 0.2},
        TAG_CORE_PRESSURIZER_HEATER_MODE:  {'id': 18, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 3},
        TAG_CORE_PRESSURIZER_SPRAY_CMD:    {'id': 19, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 0.0},
        TAG_CORE_PRESSURIZER_SPRAY_MODE:   {'id': 20, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 3},
        TAG_CORE_PRESSURIZER_VALVE_CMD:    {'id': 21, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 0.0},
        TAG_CORE_PRESSURIZER_VALVE_MODE:   {'id': 22, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 3},
        TAG_CORE_RELIEF_VALVE_STATUS:      {'id': 23, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 0},

        # Limits & alarm (primary)
        TAG_CORE_TEMP_OUT_MAX:             {'id': 24, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 320.0},
        TAG_CORE_PRESSURE_MAX:             {'id': 25, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 15.5},
        TAG_CORE_PRESSURE_HIHI:            {'id': 26, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 15.9},
        TAG_CORE_FLOW_MIN:                 {'id': 27, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 0.5},
        TAG_PRIMARY_RAD_ALARM_MAX:         {'id': 28, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 0.20},
        TAG_CORE_ALARM_STATUS:             {'id': 29, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 0},

        # ------- Steam Generator (secondary) -------
        # Sensors
        TAG_SG_SEC_TEMP_IN_VALUE:          {'id': 30, 'plc': 1, 'type': 'input',  'fault': 0.0, 'default': PHYSICS.SG_SEC_FEEDWATER_TEMP},
        TAG_SG_SEC_TEMP_OUT_VALUE:         {'id': 31, 'plc': 1, 'type': 'input',  'fault': 0.0, 'default': 260.0},
        TAG_SG_STEAM_PRESSURE_VALUE:       {'id': 32, 'plc': 1, 'type': 'input',  'fault': 0.0, 'default': 6.5},
        TAG_SG_LEVEL_VALUE:                {'id': 33, 'plc': 1, 'type': 'input',  'fault': 0.0, 'default': 60.0},
        TAG_SG_FEEDWATER_FLOW_VALUE:       {'id': 34, 'plc': 1, 'type': 'input',  'fault': 0.0, 'default': 0.6},  # bumped from 0.5
        TAG_SG_LEAK_MON_VALUE:             {'id': 35, 'plc': 1, 'type': 'input',  'fault': 0.0, 'default': 0.00},

        # Actuators / modes
        TAG_SG_FEEDWATER_VALVE_CMD:        {'id': 36, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 0.6},  # bumped from 0.5
        TAG_SG_FEEDWATER_VALVE_MODE:       {'id': 37, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 3},
        TAG_SG_RELIEF_VALVE_STATUS:        {'id': 38, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 0},

        # Limits (secondary)
        TAG_SG_LEVEL_MIN:                  {'id': 39, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 30.0},
        TAG_SG_LEVEL_MAX:                  {'id': 40, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 80.0},
        TAG_SG_STEAM_P_MAX:                {'id': 41, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 7.0},
        TAG_SG_STEAM_P_HIHI:               {'id': 42, 'plc': 1, 'type': 'output', 'fault': 0.0, 'default': 7.5},
    }


class Controllers:
    PLC_CONFIG = {
        SimulationConfig.EXECUTION_MODE_DOCKER: {
            1: {'name': 'PLC1', 'ip': '192.168.0.11', 'port': 502,  'protocol': 'ModbusWriteRequest-TCP'},
            2: {'name': 'PLC2', 'ip': '192.168.0.12', 'port': 502,  'protocol': 'ModbusWriteRequest-TCP'},
        },
        SimulationConfig.EXECUTION_MODE_GNS3: {
            1: {'name': 'PLC1', 'ip': '192.168.0.11', 'port': 502,  'protocol': 'ModbusWriteRequest-TCP'},
            2: {'name': 'PLC2', 'ip': '192.168.0.12', 'port': 502,  'protocol': 'ModbusWriteRequest-TCP'},
        },
        SimulationConfig.EXECUTION_MODE_LOCAL: {
            1: {'name': 'PLC1', 'ip': '127.0.0.1',   'port': 5502, 'protocol': 'ModbusWriteRequest-TCP'},
            2: {'name': 'PLC2', 'ip': '127.0.0.1',   'port': 5503, 'protocol': 'ModbusWriteRequest-TCP'},
        }
    }

    PLCs = PLC_CONFIG[SimulationConfig.EXECUTION_MODE]


class Connection:
    SQLITE_CONNECTION = {'type': 'sqlite',  'path': 'storage/PhysicalSimulation1.sqlite', 'name': 'fp_table'}
    MEMCACHE_DOCKER_CONNECTION = {'type': 'memcache', 'path': '192.168.1.31:11211',       'name': 'fp_table'}
    MEMCACHE_LOCAL_CONNECTION  = {'type': 'memcache', 'path': '127.0.0.1:11211',          'name': 'fp_table'}
    File_CONNECTION            = {'type': 'file',     'path': 'storage/sensors_actuators.json', 'name': 'fake_name'}

    CONNECTION_CONFIG = {
        SimulationConfig.EXECUTION_MODE_GNS3:   MEMCACHE_DOCKER_CONNECTION,
        SimulationConfig.EXECUTION_MODE_DOCKER: SQLITE_CONNECTION,
        SimulationConfig.EXECUTION_MODE_LOCAL:  SQLITE_CONNECTION
    }
    CONNECTION = CONNECTION_CONFIG[SimulationConfig.EXECUTION_MODE]
