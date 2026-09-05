# Decision Log

Architecture and project decisions, with rationale. Newest first.

---

## 2026-09-04 — Use benchtop PSU with CC/CV for test bench power

**Decision:** Use a 32V 10A benchtop PSU with CC/CV mode instead of the 200W LED PSU + buck converter.

**Context:** Initially planned to use a 12V 200W LED PSU (non-adjustable). Considered adding a buck converter with current limiting, but both servos are rated at 12V so no voltage step-down is needed. The bench PSU provides adjustable voltage AND current limiting in one unit, plus a real-time current readout for debugging.

**Consequences:**
- No buck converter needed (both servos are 12V)
- Current limit protects servos during testing (set to 2-3A for one servo)
- Real-time current readout helps understand servo draw characteristics
- The 200W LED PSU is not used for the test bench
- For the full robot (Phase 7), a different high-current power solution will be needed (bench PSU is not practical to mount in a robot)

---

## 2026-09-04 — Two URT-1 adapters, one per servo family

**Decision:** Use separate URT-1 adapters for the STS3215 arm and HLS3950 arm.

**Context:** The STS3215 uses the SCS/TTL protocol. The HLS3950 likely uses a different protocol (unconfirmed). Even if protocols were the same, running two arms independently with separate adapters is cleaner. Arms are never run simultaneously.

**Consequences:**
- Need two URT-1 adapters total (one per arm)
- USB device naming may need udev rules for stable identification (Phase 7)
- Each URT-1 handles only its servo family's channel

---

## 2026-09-04 — Run control software inside the Docker container

**Decision:** Develop and run the servo control code inside the OpenChamber Docker container, with USB device passthrough.

**Context:** The container is isolated from the host and network (only exposed over Tailscale). The user wants everything to live in the container. USB devices can be passed through via a `devices:` block in docker-compose.yml.

**Consequences:**
- Need a `devices:` block in host docker-compose.yml (requires human approval before adding)
- Latency is not a concern — Feetech servos are position-commanded, not hard real-time control loops
- udev rules for stable device naming would live on the host (outside the container)
- Development and deployment happen in the same environment

---

## 2026-09-04 — Keep paired servos as independent actuators in code

**Decision:** Paired servos (J2, J3) are independent actuators with separate bus IDs, not hardcoded as master/slave.

**Context:** The backlash reduction technique requires driving paired servos with a small angular offset. If servos are hardcoded as master/slave, the offset can't be applied independently. Keeping them as separate actuators allows the offset to be a software layer added in Phase 6.

**Consequences:**
- Each servo in a pair is addressed individually
- Backlash-offset logic is a separate layer (Phase 6), not part of the servo backend
- Slightly more complex command path for paired joints, but much more flexible

---

## 2026-09-04 — Clone GradientOS upstream, not a fork

**Decision:** Clone the upstream GradientOS repo from GitHub. Fork created later.

**Context:** The user has permission to edit their own fork but didn't have one yet. Starting with the upstream clone is simpler. Fork was created on 2026-09-04 as `GradientOS-feetech`.

**Consequences:**
- Fork: `john-semple/GradientOS-feetech` on GitHub
- Working clone: `/home/ubuntu/workspaces/GradientOS/` (origin = fork, upstream = original repo)
- Edits push to the fork; upstream changes can be pulled and merged

---

## 2026-09-04 — GradientOS is a separate repo, not inside robot-arm/

**Decision:** GradientOS is cloned as a sibling folder, not inside the robot-arm project.

**Context:** robot-arm/ is the user's own project (docs, sprints, Feetech driver code). GradientOS is a separate codebase that will be modified. Keeping them separate respects the boundary between "my project" and "upstream code I'm modifying."

**Consequences:**
- `/home/ubuntu/workspaces/robot-arm/` — this project (docs, sprints, code)
- `/home/ubuntu/workspaces/GradientOS/` — working fork (edits, push to fork)
- `/home/ubuntu/workspaces/GradientOS-upstream/` — clean reference (pull-only)
- Edits to GradientOS happen in the fork with its own git history

---

## 2026-09-04 — Two copies of GradientOS: fork + upstream reference

**Decision:** Keep two clones of GradientOS — a working fork and a clean upstream reference.

**Context:** The user wants to track upstream improvements while working on their own modifications. Standard open-source workflow: fork for edits, upstream for tracking changes.

**Consequences:**
- `GradientOS/` (fork) — `origin` points to `john-semple/GradientOS-feetech`, `upstream` points to `gradient-industrial-robotics/GradientOS`. Edits and commits go here.
- `GradientOS-upstream/` — tracks `gradient-industrial-robotics/GradientOS` only. Pull-only reference, never edited.
- To merge upstream improvements into the fork: `git pull upstream master` in `GradientOS/`.
- `GradientOS/` is excluded from the `robot-arm/` repo via `.gitignore`.