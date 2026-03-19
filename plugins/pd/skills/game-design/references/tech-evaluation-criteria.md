# Technology Evaluation Criteria

## Evaluation Dimensions

Technology-agnostic questions for evaluating game engines and development platforms. Use these dimensions to structure research — actual engine/platform recommendations come from live internet research, not this file.

### Rendering Capabilities
- Does the engine support 2D rendering with tile maps and sprite sheets?
- Does the engine support 3D rendering with modern lighting and shading?
- What level of visual fidelity is achievable within performance budgets?
- Does the engine support the target art style (pixel art pipeline, PBR materials, 2D skeletal animation)?

### Cross-Platform Support
- Is cross-platform mobile + desktop deployment supported?
- What is the build pipeline complexity per additional platform?
- Does the engine support console exports, and what are the certification requirements?
- Is web/browser export available for accessibility and demo distribution?

### Physics and Simulation
- Does the engine include built-in physics (rigid body, collision, raycasting)?
- Is the physics system suitable for the game's core mechanics (platformer physics, vehicle simulation, ragdoll)?
- Can physics be customized or replaced for genre-specific needs?

### Asset Pipeline
- What is the asset import pipeline for sprites, 3D models, audio, and animations?
- Does the engine support hot-reloading for rapid iteration?
- What file formats are natively supported?
- Is there a built-in level/scene editor?

### Community and Ecosystem
- How large is the developer community (forums, tutorials, third-party assets)?
- Is there a marketplace or asset store for accelerating development?
- What is the quality and currency of official documentation?
- Are there active community channels for troubleshooting?

### Licensing and Cost
- What is the licensing cost for a solo developer?
- Are there revenue-based royalties or thresholds?
- Is the source code available for inspection or modification?
- What are the terms for commercial release?

### Multiplayer and Networking
- Does the engine support real-time multiplayer networking?
- What networking models are available (client-server, peer-to-peer, relay)?
- Is there built-in matchmaking or lobby support?
- What is the complexity of adding multiplayer to a single-player foundation?

### Scripting and Programming
- What programming languages are supported?
- Is visual scripting available for rapid prototyping?
- What is the debugging and profiling toolchain?
- How steep is the learning curve for a developer new to the engine?

## Solo Developer Constraints

Questions to evaluate whether a technology choice is feasible for a one-person team:

### Learning Curve
- How long from zero experience to a functional prototype?
- Are there comprehensive tutorials and getting-started guides?
- Does the community produce beginner-friendly content?

### Asset Pipeline Complexity
- Can a solo developer manage the full asset pipeline (art → engine → build)?
- Are there tools or workflows that reduce asset production bottlenecks?
- Does the engine support procedural content generation to reduce manual asset creation?

### Deployment Difficulty
- How many steps from "game works in editor" to "game published on store"?
- Are platform-specific builds automated or manual?
- What platform-specific compliance requirements exist (console certification, app store review)?

### One-Person Workflow Feasibility
- Does the engine require multiple specialized roles (programmer + artist + designer), or can one person fill all roles effectively?
- Are there built-in tools for areas outside the developer's expertise (audio middleware, animation tools, UI builders)?
- What is the maintenance burden for engine updates and dependency management?

## Performance Considerations

### Target Hardware Tiers
- **Low-end mobile:** 2GB RAM, integrated GPU, limited battery — requires aggressive optimization
- **Mid-range PC:** 8GB RAM, dedicated GPU — comfortable for most indie 2D/3D games
- **High-end PC/Console:** 16GB+ RAM, modern GPU — enables demanding visual effects
- **Web browser:** Memory-constrained, no GPU compute guarantee — suitable for lightweight 2D

### Network Requirements
- Offline-capable vs. always-online — impacts accessibility and player trust
- Bandwidth requirements for multiplayer (per-player data rate)
- Server infrastructure costs for online features
- Latency tolerance by genre (fighting games <50ms, turn-based tolerates >200ms)

### Storage Footprint
- Mobile install size expectations (<100MB ideal, <500MB acceptable, >1GB high friction)
- PC/Console install size (less constrained but affects download conversion)
- Asset streaming vs. upfront download trade-offs
- Patch/update size management for live service games
