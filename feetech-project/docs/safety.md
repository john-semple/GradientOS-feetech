# Safety

Read this before any wiring, power-on, or servo commands.

## Power

### Test bench power (Phase 1-2)

- **Power source:** 32V 10A benchtop PSU with CC/CV mode
- **Set voltage to 12V** (both STS3215 and HLS3950 are rated at 12V — verify with multimeter before connecting servos)
- **Set current limit low to start:** 2-3A for a single servo. Raise as needed after observing real draw.
- **The URT-1 does NOT regulate voltage.** It passes through whatever you feed its servo-power terminal directly to the servos. The PSU IS the voltage/current regulation.
- **Verify voltage with a multimeter** at the URT-1 servo-power terminal before plugging in any servo. Some STS3215 variants in the wild are rated 6-8V, not 12V. Confirm yours is the 12V version.

### Full arm power (Phase 7, future)

- The URT-1's servo-power port has a **6A overcurrent limit**. This is fine for 1-2 servos but NOT enough for 8 servos.
- At scale, bypass the URT-1's power path: feed the PSU directly to a servo power bus/backbone, and let the URT-1 handle only signal lines.
- URT-1 signal ground must tie to the servo bus ground for common reference.

### What not to do

- **Never** feed more than the servo's rated voltage. Verify with a multimeter first.
- **Never** power servos from the USB port — USB provides only 500mA (protected), for the URT-1's logic side only.
- **Never** reverse polarity on the servo power terminal. The URT-1 has anti-reverse design but don't rely on it.
- **Never** exceed the URT-1's 6A port limit at scale without bypassing to a direct power bus.

## Wiring

- **Common ground is critical.** PSU negative, URT-1 ground, and servo bus negative must all be tied together.
- **Check continuity with a multimeter** before applying power. Verify V+ and GND are on the correct terminals.
- **One servo first.** Start with a single servo on the bus. Add more only after the first one responds correctly.
- **Disconnect power before changing wiring.** Always.

## Servo operation

- **Start with small moves.** First commands should be 1-5 degree positions, not full-range swings.
- **Watch for stalling.** A stalled servo draws stall current (~2.5A for STS3215) continuously and will overheat. If a servo doesn't move, cut power.
- **Mind the current readout.** The bench PSU shows live current. If it spikes unexpectedly, cut power immediately.
- **Servos get hot.** During extended testing, touch-test the servo body. If too hot to hold, stop and let it cool.

## Docker / host

- **Do not** edit the host `docker-compose.yml` without explicit human approval.
- **Do not** change the locked network binds (`127.0.0.1:4095`, `100.121.188.134:4095`).
- **Do not** publish `4095:4095` or `0.0.0.0:4095` (campus LAN exposure).
- **Do not** use Tailscale Funnel (public internet).
- USB device passthrough requires a `devices:` block in docker-compose.yml — needs human approval before adding.

## E-stop habits

- Keep the bench PSU's output switch within reach.
- If anything smells, smokes, or makes unexpected noise — cut power first, investigate second.
- Never walk away from the test bench with power on and servos connected.