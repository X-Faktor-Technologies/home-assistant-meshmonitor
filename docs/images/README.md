# Screenshot notes for contributors

This page records how the documentation screenshots were made and what to
check before replacing them. The screenshots use made-up mesh data so the
documentation does not expose a real network.

The four panel screenshots in this directory use the integration's real
frontend with a hand-written fictional data set. They show 28 fictional nodes,
26 fictional positions, and a mixture of Meshtastic, MeshCore, and Reticulum
activity. The names, IDs, messages, times, telemetry, links, and coordinates
were invented for these images.

The map uses the **Neutral Dark** style and OpenStreetMap tiles. Its coordinates
were chosen only for the screenshot and do not represent a real mesh network or
the project's developers. Map attribution remains visible in the image.

The setup images are cropped from Home Assistant's real integration dialogs.
The connection fields are empty, no credentials are visible, and the page
behind each dialog is excluded. The server-settings description reflects the
wording included with the same documentation update.

These images explain the interface; their counts and values are examples, not
a coverage or performance claim. Before replacing one, review every visible
field and its Markdown alt text. Do not use live mesh data unless every value
has been irreversibly sanitized.

The images were prepared on 2026-08-23. The panel was checked at 1440×900 and
390×844 with no page-level horizontal overflow.

SHA-256 checksums:

- `d69cdf0e0745be1b1bd283150dab9a44b03870dc977128c9dcae0d5f45b945d9`
  (`panel-overview.png`)
- `b58ad4f90225e0a5b78e6e930d923049f11c104c389480014648c8bc2cadc06b`
  (`panel-conversations.png`)
- `34d2a8beab77e3f556ed4dbe7fcd187b52db081288108f7a7baef2ec98f41e28`
  (`panel-nodes.png`)
- `d2efe2ec94968e5ae662756a24bda774de1463a1e177b9134bca4745d6c2c974`
  (`panel-map.png`)
- `a0fcc4ba87a31bbc76ff580edb8a9693c4f6c803fefba11ebce8edcd9aa6593a`
  (`setup-find-integration.png`)
- `a10bac251bec19ca5db17fade56c1ef9e51f464d9fa3ca0d03170263365e54f2`
  (`setup-connect.png`)
- `df02760228ad6d0cab90acaaa925780f1a555572b19484a682a43c7454f26724`
  (`setup-options-menu.png`)
- `7c41f506381432ea94b0e66159bae3886bc88642893978a0226b5128f9fc646b`
  (`setup-server-settings.png`)
