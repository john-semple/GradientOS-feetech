# Feetech HLS Protocol

Documentation of the HLS serial servo protocol used by the HLS3950M.

> This file is a stub. The HLS protocol is the **biggest unknown** in the project. It will be researched in Phase 2 (sprint-02-servo-protocol.md).

## Overview

- **Protocol family:** HLS (newer Feetech line, NOT SCS/STS or SMS)
- **Physical layer:** TBD — unknown if TTL, RS485, or other
- **Baud rate:** TBD
- **Bus addressing:** TBD

## Relationship to SCS/STS protocol

**Unknown.** Key question: does the HLS3950 share the SCS frame format and register map, or does it use an entirely new protocol?

Evidence it may differ:
- The "HLS" prefix is a distinct family naming, not SCS or SMS
- The URT-1 manual covers only SMS and SCS series — HLS is not mentioned
- The product code format (HL-3950-C001) differs from SCS/STS naming

Evidence it may share something:
- Same manufacturer (Feetech/FeiTe)
- May use the same TTL single-wire physical layer even if the protocol differs

## Research plan

1. **Feetech wiki** — check wiki.aifitlab.com for HLS documentation
2. **Feetech FD software** — download and check if it supports HLS servos; if so, it may reveal the protocol
3. **Online search** — look for community projects, datasheets, or forum posts about HLS servos
4. **Logic analyzer** — if no documentation exists, capture serial traffic between the Feetech app and the servo to reverse-engineer the protocol
5. **Feetech support** — contact Feetech directly for protocol documentation

## What we need to learn

- [ ] Physical interface (TTL 3-pin, RS485 4-pin, or other)
- [ ] Frame format (header, ID, command, parameters, checksum)
- [ ] Register map (position, speed, torque, feedback, etc.)
- [ ] Baud rate (default and configurable)
- [ ] Whether any existing Python library supports HLS servos
- [ ] Whether the URT-1 can drive HLS servos or if a different adapter is needed
- [ ] Whether the protocol is close enough to SCS to share a codebase or needs a completely separate implementation