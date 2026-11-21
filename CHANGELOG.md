# Changelog

## [0.2.0](https://github.com/svalbard-watch/swi-metobs-caching/compare/0.1.0...0.2.0) (2026-11-12)


### Features

* add apply_qc to drop sentinel and out-of-range values ([8791d00](https://github.com/svalbard-watch/swi-metobs-caching/commit/8791d00139ec849d00483da463c6e6e2cff6bd3f))
* add IWOOSNetcdfSource for IWOOS buoys on THREDDS ([e74f3e3](https://github.com/svalbard-watch/swi-metobs-caching/commit/e74f3e3a463fa021010b00515ef338a79f6762c6))
* add UNISPortalSource for the UNIS observations portal ([281ab08](https://github.com/svalbard-watch/swi-metobs-caching/commit/281ab081a34383e40ad3e4818ac98467df64bb00))
* filter implausible IWOOS readings and collapse the thermistor string ([55118e0](https://github.com/svalbard-watch/swi-metobs-caching/commit/55118e04c8939b0a08f720f46449f122cef5b833))
* IWOOS buoys and UNIS portal data sources, with minimal QC ([ff787c6](https://github.com/svalbard-watch/swi-metobs-caching/commit/ff787c6ab6ca224c3b3cb11178cd9f906e0f0e88))
* load variable limits from the variable catalogue ([0f6aa4a](https://github.com/svalbard-watch/swi-metobs-caching/commit/0f6aa4a0f37a2853a2f5a90a7278e9e566b2f8a0))


### Bug Fixes

* do not abort hourly caching when one station fails ([4389687](https://github.com/svalbard-watch/swi-metobs-caching/commit/438968776c0fbe0330dd275889f4f6fb47e1c27b))
* **docker:** apply Debian security updates in the runtime image ([4231668](https://github.com/svalbard-watch/swi-metobs-caching/commit/423166855e2cbfc9b814909457b869d9b86f5cb5))
* return UTC-aware indexes from the IWOOS and UNIS sources ([161e201](https://github.com/svalbard-watch/swi-metobs-caching/commit/161e201332d12235fd0cfd30a7f04012becb23c0))

## [0.1.0](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-caching/compare/0.0.6...0.1.0) (2026-10-12)


### Features

* **docker:** run the cron job as an unprivileged user ([4b6d417](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-caching/commit/4b6d417c2de659a3edf3388e0354f9e4d5bab114))
* **docker:** run the cron job as an unprivileged user ([c517542](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-caching/commit/c517542593eb68171cdda070e7d1a89e09af95a6))

## [0.0.6](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-caching/compare/0.0.5...0.0.6) (2026-10-11)


### Bug Fixes

* **deps:** refresh uv.lock to current releases ([a6e8c5c](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-caching/commit/a6e8c5c029e6bf2fca0e07699e2859ccbfd30453))

## [0.0.5](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-caching/compare/0.0.4...0.0.5) (2026-08-29)


### Bug Fixes

* publish images as a same-run job instead of a separate tag trigger ([450ffdb](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-caching/commit/450ffdbcf9a233d1fa2e4d35cfbddb88d468bbef))

## [0.0.4](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-caching/compare/0.0.3...0.0.4) (2026-08-29)


### Bug Fixes

* enable Swarm cron deployment and fix coverage config ([5c0a085](https://github.com/UNIS-Svalbard-Weather-Information/swi-metobs-caching/commit/5c0a0853c055859b047ae527ee66124cc5944a31))
