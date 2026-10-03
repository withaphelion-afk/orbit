---
title: Orbit
colorFrom: gray
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# Orbit

The web terminal and API of [Orbit](https://github.com/withaphelion-afk/orbit), built from GitHub.

Don't edit this Space by hand: `.github/workflows/deploy-space.yml` in the
GitHub repo overwrites it on every push to `main`. Configuration lives in the
Space's settings: secrets `ORBIT_DATA_TOKEN` and `ORBIT_DISPATCH_TOKEN`, variable
`ORBIT_DATA_REPO`. See the GitHub README, "Free cloud hosting".
