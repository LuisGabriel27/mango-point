# MangoPoint logo

The current icon is the owner-supplied [mangopoint-logo-v3.png](../../frontend/public/brand/mangopoint-logo-v3.png), added on 25 October 2026 from `Mango map-pin icon, transparent.png`. The 1254 x 1254 RGBA PNG is copied unchanged, including its transparency. It is used in navigation, login/recovery pages, the browser favicon, installed-app manifest and simulation reports. The login and navigation wordmarks render MangoPoint as accessible live text alongside the icon.

## Login layout

Login and account recovery use MangoPoint's light green background on the
left and a white form on the right. The two backgrounds fill the viewport
without an outer frame or divider border. The left panel pairs a compact
headline and feature list with three overlapping,
rounded orchard photos. On smaller screens the logo sits above the form and
the collage and feature text are hidden. Rounded fields and a green sign-in
button retain the application's colors; the page has no photo background.
The logo subtitle and the bottom orchard-management tagline have been removed.
The larger collage and the headline/feature block share the available space
below the logo; the collage still scales down with screen height.
The collage is capped at 560 px and uses more of the left panel; feature
descriptions give way to compact labels on shorter desktop screens.

The photo assets are unchanged copies of the owner-supplied images, displayed
and cropped using CSS:

- `DJI_0620.JPG` → [login-orchard-canopy.jpg](../../frontend/public/brand/login-orchard-canopy.jpg)
- `DJI_0661.JPG` → [login-orchard-river.jpg](../../frontend/public/brand/login-orchard-river.jpg)
- `dji_fly_20260508_092904_664_1778203967348_photo_optimized.jpg` → [login-orchard-trees.jpg](../../frontend/public/brand/login-orchard-trees.jpg)

The original photos in Downloads are unchanged. The collage images load
lazily, with fixed layout dimensions to avoid moving the form while loading.
The sign-in layout adapts to screen height: the collage shrinks, features
become compact labels and secondary text is omitted on shorter screens.
In narrow landscape windows the username and password fields sit side by
side, keeping the sign-in controls visible without page scrolling.
The desktop footer sits within the white form side, while the green panel
extends to the bottom of the screen. On smaller screens the green logo area
sits above the white form; both span the full width.

## Previous assets

The earlier assets below were created with the built-in image generation tool and remain available as design references. They are no longer used by the application.

Full logo with name: [mangopoint-wordmark-v3.png](../../frontend/public/brand/mangopoint-wordmark-v3.png), a 2172 x 724 PNG. See [wordmark prompts](wordmark-prompts.md).

Previous icon: [mangopoint-logo-v2.png](../../frontend/public/brand/mangopoint-logo-v2.png).

## Generation prompt

```text
Use case: logo-brand
Asset type: production logo symbol for MangoPoint, a GIS-based mango orchard pest monitoring and forecasting web application.
Primary request: create a refined, professional, distinctive new logo icon combining a mango fruit and a geographic location point in one cohesive silhouette.
Style/medium: premium minimal flat vector-style brand mark rendered as a crisp high-resolution PNG, clean confident curves, precise geometry, excellent optical balance, readable at 32 pixels.
Subject: an elegant softly asymmetric golden mango body that subtly tapers into a map-pin point, a single small circular negative-space location counter inside the upper-middle of the fruit, and one simple angled green leaf above. Integrate the ideas naturally; keep the silhouette recognizably a mango, with a softly curved lower tip. The leaf and body should have a small clean separation. Compact, bold, restrained, no thin strokes or tiny details.
Color palette: solid warm mango gold #E9AC22 for the mango body and solid fresh botanical green #78AB57 for the leaf, chosen to complement the app's existing deep forest green #1B4332 and white surfaces.
Composition/framing: one centered icon only, square 1024 by 1024 canvas; symbol occupies approximately 84 percent of canvas height with balanced narrow transparent margins. No wordmark because the app renders its MangoPoint wordmark separately.
Scene/backdrop: genuinely transparent alpha background, including the circular cutout; no background color, no checkerboard painted into the image.
Constraints: no text, no letters, no slogans, no mockup, no multiple variations, no presentation board, no outline border, no gradients, no shadows, no glow, no metallic effects, no 3D, no texture, no realistic fruit, no insect illustration, no watermark. This is a brand-new logo, not an edit of the previously viewed image.
```

## Refinement prompts

```text
Use case: precise-object-edit
Input image 1: edit target, the new MangoPoint mango/location logo.
Polish this exact logo for production. Preserve its silhouette, position, size, mango body, leaf, and circular counter. Change only the rendering cleanup: remove every speckle and stray colored pixel inside the circular hole and between the leaf and body; make those areas fully transparent. Make the interior circle perfectly clean, smooth and empty. Flatten the two colored shapes to solid mango gold #E9AC22 and botanical green #78AB57, with smooth antialiased edges, no texture or gradients. The entire outside background must remain genuinely alpha transparent. Keep the existing balanced square composition. No text, no added elements, no shadow, no background, no redesign.
```

```text
Use case: background-extraction
Input image is the edit target: the polished gold mango map-pin logo with one green leaf.
Remove the entire gray-and-white checkerboard background from this logo, both outside the symbol and inside the circular hole, and output a PNG with a genuinely transparent alpha channel. The checkerboard in the source is unwanted painted background; erase it completely, not merely replace it with another visible background. Preserve the mango and leaf colors, geometry, size and composition exactly. Keep only the solid gold mango and green leaf with clean antialiased contours. Empty pixels must have alpha zero. No shadow, no halo, no colored speckles, no backdrop, no text.
```
