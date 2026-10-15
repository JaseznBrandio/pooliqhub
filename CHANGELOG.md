# Changelog

## 0.4.2

- Boost start and stop no longer show a "Timeout" error. The unit carries them out but never sends a reply, so Home Assistant now sends the command and confirms it from the unit's status instead of waiting 10 seconds.
- Buttons respond faster for the same reason.
- Default polling is now every 30 seconds (was 5 minutes), so changes made in the Pool IQ app or on the unit show up quickly. Existing installs on the old default move to 30 seconds automatically.
- While a fault is active, Home Assistant checks every 10 seconds, so it sees the unit clear the fault and restart.
- New **Salt test result** sensor: the figure the unit and the Pool IQ app show at the end of a salt test. Shown on the Pool IQ page as "Last salt test".
- New **Fault** sensor in plain words (16 = Low flow); codes not yet known show as "Code N".

## 0.4.1

- Chlorinator status now follows the unit through purge, boost and salt test. After any command, Home Assistant checks every 5 seconds for 90 seconds, and keeps checking every 10 seconds while the unit is purging or running a salt test.
- New **Power pack temperature** sensor for chlorinators, also shown on the Pool IQ page.
- Generic device naming: Pool IQ Controller, Pool IQ Chlorinator, or Pool IQ Device for anything else. Rename a device in Home Assistant and the Pool IQ page follows.
- Setup form now describes any Pool IQ Hub device and explains adding one entry per device.
- README and install guide updated for multiple device types.

## 0.4.0

- Salt chlorinator support: mode (On / Off / Auto), output setpoint, winter and spa modes, pH dosing, boost, salt test, timers and special mode.
- Chlorinator section on the Pool IQ page.
- Number and button entities.
- Pool IQ Hub branding throughout.

## 0.3.x

- Pool IQ sidebar page with temperatures, status and socket controls.
- Login details entered during setup instead of built in, so the repository can be public.
- Installable through HACS.

## 0.2.x

- Socket control: on/off switch and On / Off / Auto mode for each socket.

## 0.1.0

- First release: read-only temperatures, salt level, output and status.
