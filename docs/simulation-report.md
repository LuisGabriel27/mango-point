# Orchard simulation report

Open **Print report** from a saved or current simulation. The final result is
selected by default; a displayed playback hour can be selected when available.
Add a reference, preparer, organization, reviewer, field observations and planned
actions before exporting. These optional fields belong to the current export;
they do not change the saved simulation or create an approval record.

The default A4 portrait report uses a compact layout inspired by the team's
modernised report template: a dark green header, amber section markers, clear
result cards and an inspection checklist. Standard reports are designed for
two pages; long names/notes or optional tables may require more pages.

1. **Map and results:** orchard, pest, modeling method, forecast/reporting hour,
   modeled outcomes, repeated-run range where saved, orthophoto, legend, first
   five priority locations and the suggested next field-check step.
2. **Sources, settings and follow-up:** source basis/counts and first six IDs per
   group, presence assumptions, saved scenario settings, weather at the reported
   hour, a three-step action plan, optional crop-impact estimates, preparer notes,
   review/signature spaces, model version, run identity and thresholds.

Select **Include detailed tables** to attach all saved sources, zone records,
custom weather periods, sampled progression and full saved model interpretations.
The checkbox starts unchecked. Compact source groups disclose when additional
IDs are omitted; missing details remain Not recorded rather than implying absence.
Supporting tables and long notes continue onto additional pages. The PDF includes
page numbers and the record reference. Empty optional notes do not create large
blank writing areas. The map and logo are embedded in the downloaded PDF, which
can be opened or printed without reconnecting.

## Orthophoto map

The report map uses the orchard orthophoto and simulation overlays on a white
background. It does not load or capture Esri satellite or OpenStreetMap tiles.
The normal interactive dashboard map retains its existing basemap. Source badges,
tree markers, shading, zone outlines and the north arrow are included in the capture.

If a supplied orthophoto fails to load, export reports an error and permits retry
instead of substituting a basemap. A run without an orthophoto is labelled as
simulation locations on a white background. The capture's attribution describes
the imagery actually included.

## Sources and actions

The source summary separates **Recorded / selected infected**, **History
Infected**, **Suspect**, **Assumed / fallback**, and other source inputs if present.
An assumed fallback remains assumed even if its simulated starting status is
infected. Infected input records are not independent proof of adult presence.
Historical and suspect probabilities are scenario assumptions; per-location
settings take precedence over displayed defaults. Detailed Active values describe
the starting realization, with unknown values labelled Not recorded.

The report's action plan is inspection guidance derived from the selected map
and pest. It prioritizes locations meeting the report screening threshold,
suggests fruitlet/bagging or mature-fruit/sanitation checks as applicable, then
asks the field team to record findings and review the scenario. It does not
claim an inspection occurred, prescribe pesticide products/doses or save actions
to orchard records. Preparer-entered follow-up notes remain separate.

Choose **Save as PDF** to download an actual `.pdf` file directly. PDF generation
runs in the browser using bundled tools, with no report upload or print dialog.
The direct download preserves the report layout as high-resolution page images;
the body text is not selectable. Longer notes may be stacked to keep them intact.

Choose **Print** to open the report tab and browser print dialog. The report tab's
button also says **Print**. Use A4 portrait at 100% scale and turn off the browser's
own headers and footers. Native printing retains selectable text when the browser
saves to PDF and repeats table headings. Its page counters use the browser's
[printed margin support](https://developer.chrome.com/blog/print-margins), verified
with the local Edge PDF exporter. Both actions use the same report content.

After pulling this frontend change, run `npm.cmd install` or `npm.cmd ci` to
install the locked `html2pdf.js` dependency. Redeploy the frontend for the new
buttons and PDF download to appear online. The PWA precaches the PDF engine with
the app assets; generating a report still requires its saved data and imagery
to be available.

Across-run frequency and one-run risk scores stay distinct. Tree states and
initial source activity describe the representative realization. The report's
50% field-check screening threshold is recorded separately from the simulation's
saved classification threshold. Neither output is a field observation.

Grid output counts cells. Crop estimates based on yield per tree are omitted for
grid reports; polygon centroids are not treated as a tree inventory. Missing
initial counts, execution dates, rainfall, humidity and other metadata remain
marked **Not recorded**. A history record's local save time is not an execution date.
