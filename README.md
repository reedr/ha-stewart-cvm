# Stewart CVM

A Home Assistant integration for the **Stewart Filmscreen CVM** screen-masking controller.
It connects to the CVM's telnet port on your LAN, logs in, and follows the masking motor.

## Entities

| Entity | What it does |
|---|---|
| `cover` Screen Mask | Position 0 is the narrowest preset and 100 the widest. Setting a position recalls the preset at or just above it. Open retracts fully, close recalls the narrowest preset, and stop halts the motor. |
| `select` Screen Aspect Ratio | Recalls the preset for the chosen aspect ratio, and shows the preset nearest the motor's current position. |

## Install

Add this repository to HACS as a custom repository (category: Integration), install
**Stewart CVM**, restart, then add **Stewart CVM** under **Settings → Devices & services**.

Setup asks for the controller's host, username and password, and two comma-separated lists
in the same order as the CVM's presets 1, 2, 3, …:

- **Preset Aspect Ratios**, e.g. `1.78,2.2,1.85,2.4,2.0,1.5`
- **Preset Motor Positions**, e.g. `5.79,1.76,5.06,0.0,3.52,8.64`

The motor positions don't need to be exact. Opening the integration's **Configure** dialog
recalibrates them by recalling each preset in turn and recording where the motor stops.

## Migrating from the old `stewart_cvm` package

The pre-HACS package (repository `reedr/stewart_cvm`) used the domain `CVM`. This one uses
`stewart_cvm`. Setup imports the old entry and keeps its device and entity IDs, so history,
areas, labels, dashboards and automations (including device-based ones) keep working.

1. Install **Stewart CVM** from HACS. It installs to the same `custom_components/stewart_cvm`
   folder and replaces the old files. Restart Home Assistant.
2. The old entry now shows as failed ("integration not found"). Leave it in place.
3. Go to **Settings → Devices & services → Add integration → Stewart CVM**, and choose
   **Import the existing CVM setup**. Its settings, including calibrated motor positions,
   are copied over.
4. The device and entities move to the new entry and the old entry is removed.

If you choose **Set up a new controller** instead, the old entities are left behind and the
new ones get new entity IDs.
