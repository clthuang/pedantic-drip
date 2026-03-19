# Aesthetic Direction Frameworks

## Art Style Taxonomy

### Pixel Art
- Retro aesthetic with defined pixel grids (8-bit, 16-bit, modern HD pixel)
- Low asset production cost per frame, high art direction impact
- Strong nostalgia appeal, indie-friendly production scale
- Suited to: platformers, roguelikes, RPGs, simulation

### Low-Poly
- Simplified 3D geometry with flat or minimal shading
- Achievable by small teams, performant on low-end hardware
- Stylized appearance ages well compared to realistic 3D
- Suited to: adventure, exploration, casual simulation

### Hand-Drawn / Illustrated
- Traditional art techniques rendered digitally (watercolor, ink, sketch)
- High per-asset cost but distinctive visual identity
- Frame-by-frame animation or rigged 2D puppets
- Suited to: narrative games, puzzle, adventure, artistic expression

### Realistic
- Photorealistic rendering with PBR materials, motion capture, volumetric effects
- Highest production cost, team size, and hardware requirements
- Uncanny valley risk for characters
- Suited to: AAA action, simulation, sports, horror

### Abstract / Minimalist
- Geometric shapes, solid colors, typographic elements
- Extremely low production cost, strong on mobile
- Gameplay clarity through visual simplicity
- Suited to: puzzle, rhythm, casual, experimental

### Mixed Media
- Combines multiple styles (pixel art with 3D, hand-drawn with photo)
- Distinctive visual identity through juxtaposition
- Risk: Inconsistency if not carefully art-directed
- Suited to: indie experimentation, narrative games, genre hybrids

## Audio Design Dimensions

### Soundtrack Style
- **Adaptive/Dynamic:** Music layers respond to gameplay state (combat intensity, exploration, danger)
- **Ambient:** Environmental soundscapes without strong melody (suited to immersion-focused games)
- **Thematic:** Distinct melodies per area, character, or emotional beat (suited to narrative games)
- **Procedural:** Algorithmically generated music that varies per session (suited to roguelikes, generative)

### SFX Categories
- **Interface:** Menu clicks, confirmations, errors — reinforce UI feedback
- **Action:** Attack impacts, movement, ability activation — convey weight and consequence
- **Environmental:** Footsteps, weather, ambient creatures — build world believability
- **Reward:** Level-up jingles, loot drops, achievement fanfares — dopamine reinforcement

### Adaptive Audio
- Vertical layering: Add/remove instrument tracks based on game state
- Horizontal re-sequencing: Branch between musical sections at transition points
- Stinger system: Trigger short musical phrases on specific events
- Consider: Silence as a deliberate design choice (tension, contrast, focus)

### Ambient Design
- Spatial audio positioning (3D soundscapes for immersion)
- Day/night audio cycles
- Dynamic weather sounds
- Environmental storytelling through sound (distant battles, wildlife, machinery)

## Game Feel/Juice

### Input Responsiveness
- Input latency target: <50ms for action games, <100ms for strategy
- Visual feedback on every input (button press → immediate screen response)
- Input buffering: Accept inputs slightly before/after the exact frame
- Coyote time: Brief grace period after leaving platform edge

### Particle Effects
- Hit sparks, dust clouds, trail effects, ambient particles
- Scale particles to action importance (small hit → few particles, critical hit → explosion)
- Color-code particles to communicate information (damage type, rarity, element)

### Screen Shake
- Brief camera displacement on impactful events (hits, explosions, landings)
- Intensity proportional to event significance
- Directional shake toward impact source
- Always provide option to reduce or disable (accessibility)

### Animation Easing
- Anticipation (wind-up before action)
- Follow-through (overshoot and settle after action)
- Squash and stretch (convey weight and elasticity)
- Ease-in/ease-out curves on all transitions (never linear unless intentional)

### Haptic Feedback
- Controller vibration patterns for key events
- Varying intensity and duration per action type
- Mobile: Taptic patterns for UI and gameplay feedback
- Consider: Haptic as information channel (directional damage, proximity alerts)

## Mood-to-Genre Mappings

| Mood | Visual Treatment | Audio Treatment | Genre Fit |
|------|-----------------|-----------------|-----------|
| Tense/Horror | Dark palette, limited visibility, grain/noise | Dissonant ambient, sudden stingers, silence | Survival horror, thriller |
| Joyful/Playful | Bright saturated colors, rounded shapes, bouncy animation | Upbeat tempo, major keys, cartoonish SFX | Platformer, casual, party |
| Epic/Grand | Wide vistas, dramatic lighting, scale contrast | Orchestral swells, choir, timpani percussion | RPG, action-adventure, strategy |
| Mysterious/Eerie | Muted cool tones, fog, obscured details | Sparse ambient, reverb, detuned instruments | Exploration, puzzle, narrative |
| Competitive/Intense | High contrast, sharp angles, UI-heavy HUD | Fast tempo, electronic beats, aggression cues | Fighting, racing, sports, FPS |
| Relaxing/Meditative | Soft pastels, gentle gradients, organic shapes | Lo-fi, nature sounds, slow tempo, gentle pads | Farming sim, idle, cozy |
| Retro/Nostalgic | Pixel art, CRT scanlines, limited color palette | Chiptune, FM synthesis, 8/16-bit sound chips | Retro-styled indie, arcade |
