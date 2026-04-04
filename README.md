# Pulse Home Assistant Integration

Pulse is a local Home Assistant integration for the Pulse ESP32 controller. It lets Home Assistant talk directly to the Pulse web API over your local network so you can:

- trigger a wake / power pulse from Home Assistant
- monitor whether the PC is currently online
- keep everything local without cloud dependencies

This integration is designed for the Pulse firmware and Windows app in the main Pulse project. The Windows app is used for configuration, while Home Assistant is used for automation and quick control.

## Features

- Local HTTP communication with the Pulse device
- `Wake PC` button entity
- `PC Online` binary sensor
- Config flow support from the Home Assistant UI
- Optional zeroconf discovery when the firmware advertises `_pulse._tcp.local`

## Entities

After setup, Home Assistant creates:

- `button.<name>_wake_pc`
  Sends a wake request to the Pulse device
- `binary_sensor.<name>_pc_online`
  Reflects the `pcOnline` value reported by Pulse

## Requirements

- A Pulse ESP32 running firmware with the web API enabled
- Pulse connected to your local Wi-Fi network
- Home Assistant able to reach the Pulse IP address over HTTP

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
4. Enter the Pulse device IP/host and port.
5. Leave token empty unless your Pulse API is later secured with one.
6. Finish setup.

## Discovery

This integration includes zeroconf discovery support, but discovery only works if the Pulse firmware is advertising the `_pulse._tcp.local` service on your network.

At the moment, Pulse firmware may still require manual setup if mDNS is disabled in the firmware build.

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

## Troubleshooting

### Home Assistant cannot connect

- Confirm the Pulse IP address is correct
- Confirm port `80` is reachable from Home Assistant
- Open `http://PULSE_IP/status` in a browser

### Wake requests fail

- Open `http://PULSE_IP/wake` in a browser on the same network
- Verify the Pulse device is still connected to Wi-Fi
- Check that the firmware web server is running and not stuck
- Update to the latest Pulse firmware and Home Assistant integration files

### Discovery does not appear

- Confirm Pulse and Home Assistant are on the same local subnet
- Confirm mDNS/zeroconf is enabled in the Pulse firmware
- If discovery is unavailable, add the integration manually by IP

## API Endpoints Used

The current integration uses:

- `GET /status`
- `POST /wake`
- `GET /wake` as a retry fallback

Expected `GET /status` response includes:

```json
{
  "wifiEnabled": true,
  "wifiConnected": true,
  "ssid": "YourWiFi",
  "ip": "192.168.1.50",
  "pcOnline": false,
  "pcStatusPin": 27,
  "pcStatusRaw": 1
}
```

## Project Status

This integration is functional and ready for HACS/manual installation, with the current entity set focused on:

- sending a wake pulse
- reporting whether the PC is online

Future expansion could include richer status, diagnostics, and more Pulse controls.
