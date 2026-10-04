# MangoPoint logo

Created with the built-in image generation tool.

Full logo with name: [mangopoint-wordmark-v3.png](../../frontend/public/brand/mangopoint-wordmark-v3.png). This 2172 x 724 PNG combines the mango symbol with the complete MangoPoint wordmark on a white background and is used on the login page. See [wordmark prompts](wordmark-prompts.md).

Icon asset: [mangopoint-logo-v2.png](../../frontend/public/brand/mangopoint-logo-v2.png).

The symbol combines a golden mango with a geographic location point and a green leaf. The navigation renders the MangoPoint wordmark as accessible live text alongside it. The icon PNG is 1254 x 1254 pixels with an alpha background and is used by the navigation and browser favicon. The login logo has the accessible image name "MangoPoint" inside the page heading. The previous logo remains at `frontend/public/mangopoint.png`.

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
