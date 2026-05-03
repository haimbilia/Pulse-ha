# Pulse Home Assistant Integration

Pulse is a local Home Assistant integration for the Pulse controller. It lets Home Assistant talk directly to the Pulse TCP control protocol over your local network so you can:

- trigger a wake / power pulse from Home Assistant
- monitor whether the PC is currently online
- keep everything local without cloud dependencies

This integration is designed for the Pulse firmware and Windows app in the main Pulse project. The Windows app is used for configuration, it is not needed in order for this integration to function.

## Features

- Local TCP communication with the Pulse device
- `Wake PC` button entity
- `PC Online` binary sensor
- Saved controller devices with `Pairing mode` and validated `Single press` binary sensors
- Live controller wake events from the firmware's `PULSE|...` stream
- Manual and firmware-triggered controller sync
- Config flow support from the Home Assistant UI
- Optional UDP discovery when the firmware replies to `PULSE_DISCOVER?` on port `4041`

## Entities

After setup, Home Assistant creates:

- `button.<name>_wake_pc`
  Sends a wake request to the Pulse device
- `button.<name>_sync_controllers`
  Refreshes the saved controller list from Pulse
- `binary_sensor.<name>_pc_online`
  Reflects the `pcOnline` value reported by Pulse
- `sensor.<name>_tcp_endpoint`
  Shows the configured TCP endpoint and event listener diagnostics
- `sensor.<name>_event_diagnostics`
  Exposes the live event listener state and last received event line
- One Home Assistant device per saved controller
  Each controller has a `Pairing mode` binary sensor. Controllers that have passed Pulse's single-press/spoofing validation also get a `Single press` binary sensor.

## Requirements

- A Pulse ESP32 running firmware with the TCP control server enabled
- Pulse connected to your local Wi-Fi network
- Home Assistant able to reach the Pulse IP address on TCP port `4040`

## Installation

### HACS

1. Open HACS in Home Assistant.
2. Open the overflow menu and choose `Custom repositories`.
3. Add this repository URL.
4. Select category `Integration`.
5. Install `Pulse`.
6. Restart Home Assistant.

### Manual

1. Copy `custom_components/pulse` into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.

Example manual path:

```text
config/custom_components/pulse/
```

## Setup

1. In Home Assistant, go to `Settings -> Devices & services`.
2. Click `Add Integration`.
3. Search for `Pulse`.
4. Enter the Pulse device IP/host and TCP port.
5. Leave token empty unless your Pulse API is later secured with one.
6. Finish setup.

## Discovery

This integration includes UDP discovery support. It broadcasts `PULSE_DISCOVER?` on port `4041` and uses the firmware's `PULSE_HERE|...|4040` response.

If discovery is unavailable, add the integration manually by IP and TCP port `4040`.

## How To Use

### Wake the PC

Use the `Wake PC` button entity from:

- the Home Assistant UI
- an automation
- a script

Example action:

```yaml
action: button.press
target:
  entity_id: button.pulse_wake_pc
```

### Check PC status

Use the `PC Online` binary sensor in dashboards, automations, or conditions.

Example condition:

```yaml
condition: state
entity_id: binary_sensor.pulse_pc_online
state: "off"
```

### Controller events

Pulse broadcasts controller wake events as plain TCP lines:

```text
PULSE|CLASSIC|dc:af:68:5f:0c:88|Wireless Controller|-64|sp=0|action=1
PULSE|CLASSIC-ACL|dc:af:68:5f:0c:88|Wireless Controller|0|sp=1|action=1
```

Home Assistant parses these live `PULSE|...` lines and briefly turns on the matching controller binary sensor:

- `sp=0` turns on `Pairing mode`
- `sp=1` turns on `Single press`

The `Single press` entity is created only after the controller is saved with `singlePressValidated=1`, which happens after the Pulse app's spoofing/single-press validation flow succeeds.

### Sync saved controllers

Saved controller sync is automatic when Pulse firmware reports `HA_SYNC|DIRTY`, for example after saving, deleting, changing actions, or completing single-press validation. The `Sync controllers` button is available as a manual refresh.

## Troubleshooting

### Home Assistant cannot connect

- Confirm the Pulse IP address is correct
- Confirm TCP port `4040` is reachable from Home Assistant
- Confirm the Pulse firmware is new enough to support multi-client TCP. The Windows app and Home Assistant can be connected at the same time.

### Wake requests fail

- Verify the Pulse device is still connected to Wi-Fi
- Check that the firmware TCP server is running and not stuck
- Update to the latest Pulse firmware and Home Assistant integration files

### Controller events do not appear

- Confirm the controller appears under the Pulse integration after `Sync controllers`
- Confirm the firmware log shows `PULSE|...` lines when the controller wakes the PC
- Check `sensor.<name>_event_diagnostics` for `last_raw_line`, `parsed_event_count`, `fired_event_count`, and `last_parsed_event`
- For `Single press`, confirm the saved controller line ends with validation `1`

### Discovery does not appear

- Confirm Pulse and Home Assistant are on the same local subnet
- Confirm UDP broadcast traffic is allowed on your network
- If discovery is unavailable, add the integration manually by IP

## TCP Protocol Used

The current integration connects to TCP port `4040` and sends line-based Pulse commands:

- `status`
- `wifi_status`
- `ha_sync_status`
- `l`
- `session_take`
- `pulse`
- `ha_sync_clear`

Expected status/list responses are the same text lines used by the Pulse Windows app, for example:

```text
STATUS|role=wifi_node|ver=1.4.0|wifi=connected|ip=192.168.1.50|bridge=idle|bt=...|owner=none
WIFI|STATUS|CONNECTED|YourWiFi|192.168.1.50|-43
aa:bb:cc:dd:ee:ff | Wireless Controller | 5s | classic | 1 | 1 | 1 | cod=0x000000
LIST_END
```

Live controller events are consumed directly from the TCP stream as `PULSE|...` lines. The firmware may also expose `ha_events [after_seq]` as an optional backlog/debug command, but normal Home Assistant automation delivery does not depend on it.

## Project Status

This integration is functional and ready for HACS/manual installation, with the current entity set focused on local TCP control, PC wake, saved controller sync, and live controller wake events.
