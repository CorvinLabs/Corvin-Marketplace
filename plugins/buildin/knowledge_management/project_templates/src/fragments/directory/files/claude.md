## Peer directory

`directory.peers` in `project.yaml` lists the peers (by id) this project may ask. It is an allowlist inside what the tenant has paired in the Agent Hub - it grants nothing new. Sending to a peer keeps its two-step confirmation and the egress gate; never send a project file to a peer without the user's explicit yes.
