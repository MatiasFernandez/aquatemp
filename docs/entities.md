# Entities

What each entity means, in terms a heat pump owner can use. Entities are grouped by where they come from; more groups can be added below.

## Pool heat pump status bits

Binary sensors for ten on/off signals the official Aqua Temp app reads from the heat pump's controller (the cloud calls them bit codes). They exist on the 30 pool heat pump products listed in [`classes.json`](../custom_components/aqua_temp/cloud/profiles/classes.json), and only on the Aqua Temp API type: Hitemp and old Aqua Temp accounts can't read bit codes. Names, polarity and defaults live in [`entity_description.pool_heat_pump.json`](../custom_components/aqua_temp/cloud/profiles/entity_description.pool_heat_pump.json).

When the cloud doesn't answer a bit, its entity is unavailable, not Off.

| Entity                                                        | Bit code                     | On means                                     | Enabled by default |
| ------------------------------------------------------------- | ---------------------------- | -------------------------------------------- | ------------------ |
| [Compressor](#compressor)                                     | `Sys1CompState`              | The compressor is running                    | Yes                |
| [Water flow](#water-flow)                                     | `WaterFlowSwitch`            | Water is flowing through the heat pump       | Yes                |
| [Inlet water temperature sensor](#temperature-sensor-faults)  | `InletWaterTempSensorFault`  | Problem: the sensor is faulty                | No (diagnostic)    |
| [Outlet water temperature sensor](#temperature-sensor-faults) | `OutletWaterTempSensorFault` | Problem: the sensor is faulty                | No (diagnostic)    |
| [Ambient temperature sensor](#temperature-sensor-faults)      | `ATSensorFault`              | Problem: the sensor is faulty                | No (diagnostic)    |
| [External stop](#external-stop)                               | `EmergencySwitch`            | Something outside the unit is holding it off | No (diagnostic)    |
| [High pressure protection](#pressure-protections)             | `Sys1HighPressureSwitch`     | Probably tripped (unverified)                | No (diagnostic)    |
| [Low pressure protection](#pressure-protections)              | `Sys1LowPressureSwitch`      | Probably tripped (unverified)                | No (diagnostic)    |
| [External mode switch](#external-mode-switch)                 | `ModeSwitch`                 | Unverified                                   | No (diagnostic)    |
| [Master unit](#master-unit)                                   | `Master/SlaveSwitch`         | This unit is the master (unverified)         | No (diagnostic)    |

The ones without a device class have no state Home Assistant could label more precisely, so they show a plain On and Off.

### Compressor

Whether the refrigerant compressor is running, as opposed to the unit being on but idle (water already at the target, or waiting for the next cycle). The official app shows "Standby" for 0 and "Running" for 1 on fixed-speed units, and the recorded responses agree: [`get_data_by_code.v5-idle.json`](../tests/cloud/fixtures/aqua_temp/get_data_by_code.v5-idle.json) reads 0 and [`get_data_by_code.v5-heating.json`](../tests/cloud/fixtures/aqua_temp/get_data_by_code.v5-heating.json) reads 1.

### Water flow

On while water flows through the heat pump, Off when the flow switch sees none (circulation pump off, closed valve, clogged filter). The bit itself is active-low: the recordings read 1 with the circulation pump off and 0 while water flowed (the idle and heating fixtures above show the same), so the entity inverts it. The official app never displays this bit, so the polarity rests on those recordings alone.

### Temperature sensor faults

Off is normal. On means the controller sees that temperature sensor as faulty (open or shorted), so its reading can't be trusted. The official app shows "--" instead of that temperature when the bit is 1. The PHNIX technical manual's fault table lists matching sensor failures: P01 inlet, P02 outlet and P04 ambient.

### External stop

A dry-contact input on the unit's board that an installer can wire to something outside the unit, such as pool automation, a timer or a stop button, to hold the heat pump off. It is not an app setting and not an automatic protection.

On means that input is holding the unit off. The official app blocks its power button then, with "Remote on/ off switch open", so turning the unit on from Home Assistant isn't expected to work either while this is On. The polarity is the app's; on products `1442284873216843776` and `1732565142225256450` the app reads the bit the other way round, and so do their profiles.

It has no problem class because it is usually set up on purpose, and it isn't called "remote" because in Home Assistant that suggests the app or the cloud.

What the input is comes from the PHNIX "Technical Manual of PC1001 (Electric Part)" (2017, [PDF](https://www.prodimar.ro/fisiere/10856_a_757681pch028manualtehnicintrorig_15762_10_1676693654.pdf)): its status list has an "S01 Emergency switch" entry (p. 32), the wiring diagram wires the board's DI01 input to a terminal block labelled "REMOTE IN" (p. 37), and it says the emergency switch can shut a running unit off (p. 7). The fault table has no code for it. That manual covers one PHNIX controller board, so your unit may differ.

### Pressure protections

Switches in the refrigerant circuit. When one trips, the unit stops; the manual's fault codes are E01 high pressure protection and E02 low pressure protection. The official app reads these bits but never shows them, so which value means tripped is unverified. That is why they have no device class and start disabled. They read On for 1.

### External mode switch

An input for choosing heating or cooling from outside the unit, through wiring (manual status list: "S05 Mode switch"). The official app only uses this bit on some other products, where 0 means heat. What it means on your unit is unverified, and it reads On for 1.

### Master unit

The master/slave selector for installations where several heat pumps work together (manual status list: "S06 Master-slave switch"). The official app only uses this bit on some other products. We read 1 as master, flipped on the two products above as the app does. Unverified.
