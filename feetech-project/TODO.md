# TODO

## Current state

**Sprint 00 (Setup & Documentation):** Complete. Repo created, docs pushed, GradientOS forked and cloned.

**GradientOS clones ready:**
- `GradientOS/` — fork (for edits), tracks `john-semple/GradientOS-feetech`
- `GradientOS-upstream/` — clean reference (pull-only)

## Next action

1. Begin Sprint 01 (Electronics Validation) when ready to wire the test bench
2. Or jump to Sprint 03 (Study GradientOS) since the clones are already here — can be done any time

## Upcoming sprints

| Sprint | Status | Description |
|--------|--------|-------------|
| sprint-00 | Complete | Setup & documentation |
| sprint-01 | Not started | Electronics validation — wire test bench safely |
| sprint-02 | Not started | Servo protocol validation — STS3215 then HLS3950 |
| sprint-03 | Not started | Study GradientOS architecture (needs human "go" to clone) |
| sprint-04 | Not started | STS3215 backend in GradientOS |
| sprint-05 | Not started | HLS3950 backend in GradientOS |
| sprint-06 | Not started | Paired-servo joint model with backlash offset |
| sprint-07 | Not started | Full 6DOF arm config & scale |

## Blocked items

- [ ] Docker USB passthrough — needs `devices:` block in host docker-compose.yml (requires human approval)
- [ ] HLS3950 protocol research — needs bench testing (Sprint 02)

## Open questions to resolve

- [ ] Confirm URT-1 USB port type (manual says Mini, user reports Micro — check the board)
- [ ] Confirm STS3215 is 12V variant (verify with multimeter before powering)
- [ ] HLS3950 protocol family, physical interface, and URT-1 compatibility