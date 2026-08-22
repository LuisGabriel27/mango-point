# Frontend map assets

`guimaras-wonders-farm-orthophoto.png` and
`guimaras-wonders-farm-trees.json` are the repository-safe runtime copies of
the Guimaras Wonders Farm map and tree dataset. The frontend imports them
directly so Vite includes them in every development and production build and
fails the build if either file is missing.

The original GeoTIFF, DTM, and DSM remain under `data/orchards/` and are
intentionally excluded from Git because they are hundreds of megabytes. Do not
move this PNG back into that ignored directory without providing another
tracked frontend copy.

Expected SHA-256:
`46df891894b26f17a4f0ff953cdbcc035a9fadf3ff8d8228abd3b0ad3a0bf945`
