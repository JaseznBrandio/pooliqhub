# Changelog

## 0.4.11

- **Changes made in Home Assistant can no longer bounce back or show a false state.** A change now shows the instant you tap it, before the cloud answers, and is held until the unit reports that same value. A stale report arriving in the meantime is ignored. If the unit hasn't confirmed within 20 seconds, Home Assistant shows what the unit actually reported, so a command that didn't take effect can't stay on screen. If the cloud rejects a command, the control goes straight back and an error is shown.
- This compares values rather than timestamps, so it works even if the Home Assistant and Pool IQ cloud clocks differ. Replaces the 0.4.10 approach, and now covers every control: sockets, power, mode, output, pH dosing and boost.

## 0.4.10

- **Fix switch bounce-back on mobile.** After tapping a pump or light switch, the UI could briefly flip back to off before settling on the correct state. A stale report already in the WebSocket pipeline was overwriting the optimistic update. The push path now rejects messages older than the last command, matching the guard polling already had.

## 0.4.9

- **Status shows every fault in plain words**, using the Pool IQ Hub fault table: high salt, low salt, extremely high salt, low flow, no output, low output, internal temp high, transformer temp high, water temp high, water temp low, water temp rising fast and check ioniser rods. When several faults happen at once they're all listed, for example "Low salt, Water temp low".

## 0.4.8

- The sidebar item is now called **Pool IQ Hub**.
- README and install guide screenshots updated to the current layout, including a phone view.

## 0.4.7

- Chlorinator readings are separated by thin divider lines instead of outlined cards, four across on wide screens and two across on narrower ones, so every row fills evenly.
- Clearer labels: Water Temp, Actual Output, Cell Status, Pump Status, Power Pack Temp.
- Buttons always show an outline, whatever the Home Assistant theme.

## 0.4.6

- **Chlorinator page redesigned.** Controls first: Power, Mode, Output and Boost on the left; readings on the right as small outlined cards (Salt Reading, water temperature, actual output, cell, pump, power pack, status). Stacks on a phone, controls on top.
- **Salt Reading card** shows "- - ppm" until a test has run, with a **Test Salt Level** button in the card.
- **Chlorine boost timer.** Set the boost duration before starting; while boost runs, a live countdown replaces it and the duration is locked until boost is stopped. Works for boosts started from the Pool IQ app too, and survives a Home Assistant restart. New **Boost ends** sensor.
- **pH dosing:** pH2 is now **Prime / Demand amount**, with its **Start Prime / Demand Dosing** button directly under it.
- **Faults** is now labelled **Status** on every device.

## 0.4.5

- **Salt** on the Pool IQ page is the salt test result, the same figure as the app. It never shows the unit's live reading; before a test it shows "Not tested". A **Run test** button sits right next to it.
- **Start boost** moved under the output control in the Chlorinator section.
- **pH dosing** laid out on one line: pH1 run time (min/day) and pH2 prime amount (ml), each with the value on top and its label below, then Start / Stop pH dose.
- Layout tuned for phones.

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
