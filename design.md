# Design System Specification: High-End Editorial Dark Mode
 
## 1. Overview & Creative North Star
**Creative North Star: The Sovereign Architect**
This design system moves away from the chaotic "neon-cyberpunk" aesthetics often found in AI tools. Instead, it adopts a high-end editorial language—think luxury Swiss horology meets modern architectural blueprints. The interface is not just a tool; it is a sophisticated environment.
 
We break the "standard SaaS template" by utilizing **intentional asymmetry** and **tonal depth**. Rather than relying on heavy lines to separate ideas, we use generous breathing room (the "negative space as a luxury" principle) and subtle shifts in surface luminance. The goal is a visual experience that feels authoritative, silent, and immensely powerful.
 
---
 
## 2. Colors
Our palette is rooted in deep blacks and charcoal greys, punctuated by high-energy electric blue accents.
 
### Tonal Logic
- **Primary (`#c5e3ff`):** Use for high-impact actions and key brand moments.
- **Surface (`#131313`):** The canvas. Everything begins here.
- **Surface Tiers:** Use `surface_container_lowest` (`#0e0e0e`) to create deep wells of content and `surface_container_high` (`#2a2a2a`) to bring interactive elements forward.
 
### The "No-Line" Rule
To maintain a premium feel, **1px solid borders are prohibited for sectioning.** Boundaries must be defined through background color shifts. For example, a content block using `surface_container_low` should sit directly on a `surface` background without a stroke. Let the change in value define the edge.
 
### The "Glass & Gradient" Rule
While we avoid heavy glassmorphism, floating elements (like dropdowns or modals) should use a subtle backdrop-blur (12px–20px) combined with a semi-transparent `surface_variant`. Main CTAs should utilize a subtle linear gradient from `primary` to `primary_container` to add "soul" and dimension, avoiding the flatness of basic digital UI.
 
---
 
## 3. Typography
The typographic system relies on the interplay between the geometric authority of **Manrope** and the functional precision of **Inter**.
 
- **Display & Headlines (Manrope):** These are your "Editorial Voice." Use `display-lg` for hero moments with tight letter-spacing (-2%). The high contrast against the dark background demands a bold weight to ensure authority.
- **Body & Labels (Inter):** Your "Functional Voice." Inter provides maximum legibility at smaller scales. Use `body-md` for standard reading and `label-sm` for technical metadata.
- **Hierarchy through Contrast:** Use `on_surface` (high contrast) for headings and `on_surface_variant` (lower contrast) for secondary descriptions. This guides the eye naturally through the information architecture.
 
---
 
## 4. Elevation & Depth
In this system, depth is a matter of **Tonal Layering**, not structural ornamentation.
 
### The Layering Principle
Depth is achieved by "stacking" surface tiers.
1. **Base:** `surface` (#131313)
2. **Structural Sections:** `surface_container_low` (#1c1b1b)
3. **Interactive Cards:** `surface_container_high` (#2a2a2a)
This creates a soft, natural lift that mimics physical material layers without the clutter of drop shadows.
 
### Ambient Shadows
When an element must float (e.g., a primary modal), use "Ambient Shadows":
- **Color:** A tinted version of the surface (e.g., `#000000` at 40% opacity).
- **Blur:** Large values (30px–60px) to simulate soft, dispersed light.
- **Spread:** Negative spread to keep the shadow tucked neatly behind the element.
 
### The "Ghost Border" Fallback
If a border is required for accessibility, use the **Ghost Border**: the `outline_variant` token at 15% opacity. This provides a "suggestion" of a boundary that disappears into the background, maintaining the "No-Line" aesthetic.
 
---
 
## 5. Components
 
### Buttons
- **Primary:** Gradient from `primary` to `primary_container`. Text in `on_primary`. Shape: `DEFAULT` (0.5rem).
- **Secondary:** Surface `surface_container_highest` with a `Ghost Border`.
- **Tertiary:** Ghost button (no background) using `primary` text.
 
### Cards & Lists
**Strict Rule:** No divider lines. Separate list items using `8px` of vertical white space or by alternating between `surface_container_low` and `surface_container_lowest`. For cards, use `lg` (1rem) roundedness to soften the technological edge.
 
### Input Fields
- **Idle:** `surface_container_lowest` background with a subtle `outline_variant` ghost border.
- **Focus:** Border transitions to `primary` (100% opacity) with a soft `primary` outer glow (4px blur).
- **Typography:** Placeholder text must use `on_surface_variant` to maintain low visual noise.
 
### Chips
Use `full` (9999px) roundedness. Use `secondary_container` for inactive states and `primary` for active selections.
 
### The "Status Orb" (Custom Component)
For AI-driven status or "agent" activity, use a 4px circular "orb" with the `tertiary` color and a subtle CSS pulse animation. This provides a "technological pulse" without overwhelming the professional tone.
 
---
 
## 6. Do's and Don'ts
 
### Do
- **Do** use `lg` (1rem) and `xl` (1.5rem) spacing to separate major themes.
- **Do** use `primary_fixed` for small highlights (like "New" tags) to provide a pop of electric color.
- **Do** align editorial headers to the left to create a strong, stable vertical axis.
 
### Don't
- **Don't** use pure white (#FFFFFF) for body text; it causes "halogen glow" on dark backgrounds. Use `on_surface`.
- **Don't** use generic "drop shadows" with 0 blur. It breaks the sophisticated architectural feel.
- **Don't** use neon greens or purples. Stay strictly within the blue/cyan and charcoal spectrum to maintain the "Professional" personality.
- **Don't** cram content. If a screen feels full, increase the page height or use a "nested" surface to hide secondary information.