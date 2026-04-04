# Frontend Design Quality

Avoid generic, on-distribution frontend output. Every surface should look intentional, opinionated, and specific to the product.

## Banned Patterns

- Default card grids with uniform spacing and no hierarchy
- Stock hero section with centered headline, gradient blob, and generic CTA
- Unmodified library defaults passed off as finished design
- Flat layouts with no layering, depth, or motion
- Uniform radius, spacing, and shadows across every component
- Safe gray-on-white with one decorative accent color
- Dashboard-by-numbers: sidebar + cards + charts with no point of view
- Default font stacks used without a deliberate reason
- Cliched color schemes, especially purple gradients on white

## Required Qualities (at least 4 of 10)

Every meaningful frontend surface must demonstrate at least four:

1. Clear hierarchy through scale contrast
2. Intentional rhythm in spacing, not uniform padding everywhere
3. Depth or layering through overlap, shadows, surfaces, or motion
4. Typography with character and a real pairing strategy
5. Color used semantically, not just decoratively
6. Hover, focus, and active states that feel designed
7. Grid-breaking editorial or bento composition where appropriate
8. Texture, grain, or atmosphere when it fits the visual direction
9. Motion that clarifies flow instead of distracting from it
10. Data visualization treated as part of the design system

## Before Writing Frontend Code

1. Pick a specific style direction. Avoid vague defaults like "clean minimal".
2. Define a palette intentionally.
3. Choose typography deliberately. Avoid Arial, Inter, Roboto.
4. Use CSS variables for all design tokens.

## Style Directions Worth Considering

Editorial / magazine, neo-brutalism, glassmorphism with real depth, dark or light luxury with disciplined contrast, bento layouts, scrollytelling, 3D integration, Swiss / International, retro-futurism.

Do not default to dark mode automatically. Choose the direction the product wants.

## Component Checklist

- [ ] Does it avoid looking like a default Tailwind or shadcn template?
- [ ] Does it have intentional hover/focus/active states?
- [ ] Does it use hierarchy rather than uniform emphasis?
- [ ] Would this look believable in a real product screenshot?
- [ ] If it supports both themes, do both light and dark feel intentional?
