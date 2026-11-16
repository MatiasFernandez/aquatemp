# Pool heat pumps

Entities on the [pool heat pump products](README.md#which-page-applies-to-your-heat-pump). See [how to read an entry](README.md#how-to-read-an-entry).

| Entity                                                              | Topic                  | Confidence |
| ------------------------------------------------------------------- | ---------------------- | ---------- |
| [Ambient temperature sensor](#ambient-temperature-sensor)           | Faults and protections | Verified   |
| [Climate entity](#climate-entity)                                   | Operation              | Verified   |
| [Compressor](#compressor)                                           | Operation              | Verified   |
| [External mode switch](#external-mode-switch)                       | Wired inputs           | Unknown    |
| [External stop](#external-stop)                                     | Wired inputs           | Verified   |
| [High pressure protection](#high-pressure-protection)               | Faults and protections | Inferred   |
| [Inlet water temperature sensor](#inlet-water-temperature-sensor)   | Faults and protections | Verified   |
| [Low pressure protection](#low-pressure-protection)                 | Faults and protections | Inferred   |
| [Master unit](#master-unit)                                         | Wired inputs           | Unknown    |
| [Outlet water temperature sensor](#outlet-water-temperature-sensor) | Faults and protections | Verified   |
| [Water flow](#water-flow)                                           | Operation              | Verified   |

## Operation

### Climate entity

Climate · enabled · **Verified**

Home Assistant shows it under the device's name. It holds the target temperature, mode and fan mode. On Aqua Temp API type accounts it also populates `hvac_action` to show what the heat pump is doing, from the [Compressor](#compressor): heating or cooling while the compressor runs, idle while it is stopped, off while the heat pump is off. In auto mode it shows idle with the compressor stopped. While it runs, it shows heating when the auto target temperature is above the inlet water temperature and cooling when it is at or below, which is our reading of the official app's rule, and nothing if either temperature is missing. A defrost cycle shows as heating, or idle if the compressor stops.

<details><summary>How we know</summary>

What it is doing comes from the compressor bit, verified as described under [Compressor](#compressor), and the mode the heat pump is set to. The cloud reports no separate heating, cooling or defrost state.

In auto mode the official app picks heating or cooling by comparing the auto target with the inlet water temperature. Its code hides which comparison it makes; we read it as heating when the target is above the inlet, which is why equal temperatures show cooling. That reading hasn't been checked against the app or a unit.

Code: the compressor role in the profile's mapping ([mapping.pool_heat_pump.json](../../custom_components/aqua_temp/cloud/profiles/mapping.pool_heat_pump.json)) names `Sys1CompState`; its catalog entry's on and off values read as running and stopped. In auto mode it also reads the auto target (`R03`) and the inlet water temperature (`T02`). The profile of product `1442284873216843776` names no inlet water temperature code, so there it shows nothing while running in auto mode.

</details>

### Compressor

Binary sensor · enabled · Aqua Temp API type only · **Verified**

On while the compressor runs. Off while the heat pump is on but idle, for example with the water already at the target temperature.

<details><summary>How we know</summary>

The official app shows "Standby" when this value is 0 and "Running" when it is 1 on fixed-speed units. Recorded responses agree: 0 while idle ([get_data_by_code.v5-idle.json](../../tests/cloud/fixtures/aqua_temp/get_data_by_code.v5-idle.json)), 1 while heating ([get_data_by_code.v5-heating.json](../../tests/cloud/fixtures/aqua_temp/get_data_by_code.v5-heating.json)).

Code: `Sys1CompState`, on for 1.

</details>

### Water flow

Binary sensor · enabled · Aqua Temp API type only · **Verified**

On while water flows through the heat pump. Off when the flow switch sees none: the circulation pump is off, a valve is closed or the filter is clogged.

<details><summary>How we know</summary>

The official app doesn't show this value. On a real unit it read 1 with the circulation pump off and 0 while water flowed, as the idle and heating recordings above show.

Code: `WaterFlowSwitch`, on for 0.

</details>

## Faults and protections

### Inlet water temperature sensor

Binary sensor · disabled by default, diagnostic · Aqua Temp API type only · **Verified**

Shows a problem when the sensor measuring the water entering the heat pump is faulty, so its temperature can't be trusted.

<details><summary>How we know</summary>

The official app shows "--" for the inlet water temperature when this value is 1. The PHNIX PC1001 technical manual lists the matching failure as fault code P01 ([PDF](https://www.prodimar.ro/fisiere/10856_a_757681pch028manualtehnicintrorig_15762_10_1676693654.pdf), p. 33).

Code: `InletWaterTempSensorFault`, problem for 1.

</details>

### Outlet water temperature sensor

Binary sensor · disabled by default, diagnostic · Aqua Temp API type only · **Verified**

Shows a problem when the sensor measuring the water leaving the heat pump is faulty, so its temperature can't be trusted.

<details><summary>How we know</summary>

The official app shows "--" for the outlet water temperature when this value is 1. The PHNIX PC1001 technical manual lists the matching failure as fault code P02 ([PDF](https://www.prodimar.ro/fisiere/10856_a_757681pch028manualtehnicintrorig_15762_10_1676693654.pdf), p. 33).

Code: `OutletWaterTempSensorFault`, problem for 1.

</details>

### Ambient temperature sensor

Binary sensor · disabled by default, diagnostic · Aqua Temp API type only · **Verified**

Shows a problem when the outdoor air temperature sensor is faulty, so its temperature can't be trusted.

<details><summary>How we know</summary>

The official app shows "--" for the ambient temperature when this value is 1. The PHNIX PC1001 technical manual lists the matching failure as fault code P04 ([PDF](https://www.prodimar.ro/fisiere/10856_a_757681pch028manualtehnicintrorig_15762_10_1676693654.pdf), p. 33).

Code: `ATSensorFault`, problem for 1.

</details>

### High pressure protection

Binary sensor · disabled by default, diagnostic · Aqua Temp API type only · **Inferred**

The switch that stops the heat pump when the refrigerant pressure gets too high. Which state means it has tripped is unknown, so it shows a plain On or Off.

<details><summary>How we know</summary>

The official app reads this value but never shows it. The PHNIX PC1001 technical manual describes the switch and its fault, E01 high pressure protection ([PDF](https://www.prodimar.ro/fisiere/10856_a_757681pch028manualtehnicintrorig_15762_10_1676693654.pdf), p. 34). It read 0 on a healthy unit.

Code: `Sys1HighPressureSwitch`, on for 1.

</details>

### Low pressure protection

Binary sensor · disabled by default, diagnostic · Aqua Temp API type only · **Inferred**

The switch that stops the heat pump when the refrigerant pressure gets too low. Which state means it has tripped is unknown, so it shows a plain On or Off.

<details><summary>How we know</summary>

The official app reads this value but never shows it. The PHNIX PC1001 technical manual describes the switch and its fault, E02 low pressure protection ([PDF](https://www.prodimar.ro/fisiere/10856_a_757681pch028manualtehnicintrorig_15762_10_1676693654.pdf), p. 34). It read 0 on a healthy unit.

Code: `Sys1LowPressureSwitch`, on for 1.

</details>

## Wired inputs

Terminals on the heat pump's board an installer can wire to other equipment.

### External stop

Binary sensor · disabled by default, diagnostic · Aqua Temp API type only · **Verified**

On when something wired to the heat pump, such as pool automation, a timer or a stop button, is holding it off. While it's on, the heat pump can't be turned on from the app, nor from Home Assistant. It isn't a fault, nor a setting in the app.

<details><summary>How we know</summary>

The official app blocks its power button with "Remote on/ off switch open" when this value says the input is holding the unit off. The PHNIX PC1001 technical manual ([PDF](https://www.prodimar.ro/fisiere/10856_a_757681pch028manualtehnicintrorig_15762_10_1676693654.pdf)) lists it as "S01 Emergency switch" (p. 32), wires it to a terminal block labelled "REMOTE IN" (p. 37) and says it can shut a running unit off (p. 7). That manual covers one PHNIX controller board, so yours may differ.

Code: `EmergencySwitch`, on for 1, or for 0 on products 1442284873216843776 and 1732565142225256450, as the app reads it.

</details>

### External mode switch

Binary sensor · disabled by default, diagnostic · Aqua Temp API type only · **Unknown**

An input for choosing heating or cooling through wiring instead of the controller. What On and Off mean on these units is unknown.

<details><summary>How we know</summary>

The PHNIX PC1001 technical manual lists it as "S05 Mode switch" (p. 32). The official app only uses this value on a few other products, where 0 means heat.

Code: `ModeSwitch`, on for 1.

</details>

### Master unit

Binary sensor · disabled by default, diagnostic · Aqua Temp API type only · **Unknown**

On when this heat pump is the master in an installation where several heat pumps work together. Unverified on these units.

<details><summary>How we know</summary>

The PHNIX PC1001 technical manual lists it as "S06 Master-slave switch" (p. 32). The official app only uses this value on a few other products, where it reads 0 as slave, or 1 on products 1442284873216843776 and 1732565142225256450. The entity follows the same reading.

Code: `Master/SlaveSwitch`, on for 1, or for 0 on those two products.

</details>
