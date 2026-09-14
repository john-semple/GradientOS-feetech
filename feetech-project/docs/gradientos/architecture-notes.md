# GradientOS Architecture Notes

> This file is a stub. It will be filled in during Phase 3 (archive/sprint-02-gradientos-study-COMPLETE.md) after cloning and studying the GradientOS codebase.

## Overview

GradientOS is a robot control system by Gradient Industrial Robotics. It currently uses EtherCAT for servo communication. The goal is to add Feetech servo support as an alternative protocol backend.

## Repository

- **Source:** `https://github.com/gradient-industrial-robotics/GradientOS.git`
- **Clone location:** `/home/ubuntu/workspaces/GradientOS/` (sibling to this project)
- **Branch:** master (per host checkout state)
- **License:** TBD — check before editing

## Architecture to document

### Overall structure
- [ ] Language(s) used (Python, C++, other)
- [ ] Core modules and their responsibilities
- [ ] Web UI structure (noted as `web-ui/` with package.json on host)
- [ ] Entry points (main scripts, services)

### Hardware abstraction layer
- [ ] How does GradientOS abstract servo communication?
- [ ] Where is the EtherCAT protocol implementation?
- [ ] Is there a protocol interface/abstract base class that new backends implement?
- [ ] What is the "build your own robot" workflow mentioned by the user?

### Joint / robot model
- [ ] How are joints defined in config?
- [ ] Can a joint map to multiple physical actuators (for paired servos)?
- [ ] Are reduction ratios, motor types, and link lengths configurable?
- [ ] How is the motion queue / trajectory planning handled?

### Safety layer
- [ ] What safety mechanisms exist (e-stop, limits, torque limits)?
- [ ] Can these be reused for Feetech servos?

### Configuration
- [ ] Config file format(s)
- [ ] How a new robot definition is created
- [ ] How servo types are specified per joint

## Notes

(Filled in during Phase 3)