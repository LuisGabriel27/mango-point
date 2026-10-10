# Orchard simulation report

Open **Print report** from a saved or current simulation. The final result is
selected by default; a displayed playback hour can be selected when available.
Add a reference, preparer, organization, reviewer, field observations and planned
actions before exporting. These optional fields belong to the current export;
they do not change the saved simulation or create an approval record.

The A4 portrait document contains:

1. Orchard and record identification, modeled outcomes, and map-value distribution.
2. A dedicated map with the selected metric, legend, source badges and attribution.
3. Saved scenario inputs, recorded hourly weather, conditional crop-impact estimates,
   observations, planned actions, and signature/date spaces.
4. Supporting run identifiers, forecast and execution dates, weather provenance,
   up to ten priority locations, all saved source/zone entries, and sampled progression.

Supporting tables and long notes continue onto additional pages. Table headings
repeat and the PDF includes page numbers and the run reference. The map and logo
are embedded in the offline HTML, so its record can be printed without reconnecting.

Choose **Print / Save PDF**, then **Save as PDF**. Use A4 portrait at 100% scale
and turn off the browser's own headers and footers. Page counters use the browser's
[printed margin support](https://developer.chrome.com/blog/print-margins), verified
with the local Edge PDF exporter. The offline report contains the same document.

Across-run frequency and one-run risk scores stay distinct. Tree states and
initial source activity describe the representative realization. The report's
50% field-check screening threshold is recorded separately from the simulation's
saved classification threshold. Neither output is a field observation.

Grid output counts cells. Crop estimates based on yield per tree are omitted for
grid reports; polygon centroids are not treated as a tree inventory. Missing
initial counts, execution dates, rainfall, humidity and other metadata remain
marked **Not recorded**. A history record's local save time is not an execution date.
