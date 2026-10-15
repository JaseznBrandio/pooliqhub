# Changelog

## 0.4.4

- **Live updates.** Home Assistant now subscribes to the Pool IQ cloud's live channel, the same one the app uses, so changes made in the app or on the unit show up within a second: power, purge, cell and pump status, mode, settings and faults. Polling continues every 5 minutes as a safety net, and takes over automatically if the live channel drops.
- **Salt test result arrives live**, with the same figure the app shows.
- **pH dosing reworked to match the app:** an on/off toggle, and while it's on, pH1 run time (min/day), pH2 prime amount (ml), and Start / Stop pH dose with the amount remaining. The prime amount is only sent when you press Start.
- **No more bouncing back.** A change made in Home Assistant is held until the unit confirms it.
- In Winter or Spa mode, the output control shows the output the unit actually reports.

## 0.4.3

- New **Mode** selector: Normal, Winter or Spa. It follows the work mode the unit reports, so changes made in the Pool IQ app show too, and Normal takes the unit back out of winter or spa mode. Replaces the separate Winter mode and Spa mode switches.
- The output control now adjusts the setting for the active mode: normal output, winter output or spa output.
- Settings the unit doesn't report back (pH dosing, winter and spa output, pH run time and dose, timer cycle) are now read from the Pool IQ cloud's record of changes. Changes made in the app show in Home Assistant, and changes made in Home Assistant no longer flip back.
- pH dosing shows when the dosing pump is running.
- Chlorinators no longer query socket history they don't have, so each check is quicker.

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
