# Screenshot notes for contributors

The panel screenshots in this directory are generated from the integration's
real frontend and a controlled synthetic data set. They must never be captured
from a live mesh network.

## Regenerate the panel screenshots

From the repository root, run:

```bash
node scripts/generate-doc-screenshots.mjs
```

The generator uses Node.js built-ins and a locally installed Chromium-family
browser. Set `CHROMIUM` to an executable path when automatic browser discovery
is not sufficient. It serves the repository only on loopback while rendering.

The fixture, browser harness, and generator are tracked under
`scripts/docs-screenshots/` and `scripts/generate-doc-screenshots.mjs`. The
fixture freezes its clock and uses invented names, IDs, messages, telemetry,
links, and coordinates so repeated runs produce reviewable images without
exposing a real system. The browser is forced to an English locale and UTC,
the harness blocks external network access, and the map uses the tile-free
privacy style.

The Overview, Messages, and Nodes captures use a 1440×900 viewport. The Map
uses 1600×900 so its filters and controls remain readable. Before committing
new images:

1. Use the same browser build, run the generator twice, and confirm the image
   hashes are unchanged.
2. Review every visible field for private data and misleading claims.
3. Check that the images match the current user guide and frontend behavior.
4. Confirm the Messages image demonstrates current focus/scroll behavior and
   the Map image visibly identifies its tile-free privacy mode.
5. Run the repository validation suite.

Panel screenshot filenames include their documentation release series. When a
panel image changes, update that suffix along with every reference so HACS and
browser caches cannot silently reuse an older image.

The checked-in panel images were rendered with Brave 152.1.94.117. A different
Chromium build may render fonts differently even when the fixture data and
layout are unchanged.

The setup images are cropped from Home Assistant's integration dialogs. Their
connection fields are empty, no credentials are visible, and the surrounding
Home Assistant page is excluded.

These images explain the interface. Their counts and values are examples, not
coverage or performance claims.

## SHA-256 checksums

- `a7e75a551e9fd0afaa1035b39ccc9caf899f1ca15302103074cc70681a74199e`
  (`panel-overview-v0.17.png`)
- `0496d3e023a20cfb3ff856db8b4eea9b6e5adcf1ab95e83dbd584df88b6d17b6`
  (`panel-conversations-v0.17.png`)
- `6440ebeab36f307568ac4b43283043b9389a1c58ea205e2ae5981779f567ceb5`
  (`panel-nodes-v0.17.png`)
- `204b1d9c513e7a50b4374d56aacf20ac273290f0815e8e4bcf601034ee1d1c63`
  (`panel-map-v0.17.png`)
- `a0fcc4ba87a31bbc76ff580edb8a9693c4f6c803fefba11ebce8edcd9aa6593a`
  (`setup-find-integration.png`)
- `a10bac251bec19ca5db17fade56c1ef9e51f464d9fa3ca0d03170263365e54f2`
  (`setup-connect.png`)
- `df02760228ad6d0cab90acaaa925780f1a555572b19484a682a43c7454f26724`
  (`setup-options-menu.png`)
- `7c41f506381432ea94b0e66159bae3886bc88642893978a0226b5128f9fc646b`
  (`setup-server-settings.png`)
