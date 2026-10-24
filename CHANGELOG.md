# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Entries up to 3.0.37
predate this fork and keep their original format.

## [Unreleased]

### Changed

- Require Home Assistant 2025.11 or newer (was 2024.1)

### Security

- Stop logging config and options flow input, which included the plaintext password; only the API type and session-token toggle are logged on submit

## [3.1.0] - 2026-10-24

_First release of the [MatiasFernandez/aquatemp](https://github.com/MatiasFernandez/aquatemp) fork, based on upstream 3.0.43_

### Added

- Allow parameter JSON files to override `entity_category` and `state_class` per sensor
- Document login failures caused by passwords longer than 16 characters
- Opt-in option to log the session token at WARNING level, for making manual API requests without logging the integration out

### Changed

- Promote inlet, outlet and ambient water temperatures to primary sensors with long-term statistics
- Point manifest documentation, issue tracker and code owner at this fork
- Saving options reloads the integration, so changes take effect without a manual reload

### Fixed

- Keep target temperature visible and editable when HVAC mode is OFF

## [3.0.43] - 2026-05-12

_Released in [tkejzlar/aquatemp](https://github.com/tkejzlar/aquatemp)_

### Added

- DEBUG-level login-failure diagnostics that log the shape of the credentials (length, encoding, whitespace), never their content

## [3.0.42] - 2026-05-12

_Released in [tkejzlar/aquatemp](https://github.com/tkejzlar/aquatemp)_

### Added

- Support for product ID 1845987289788989441 [PR #1](https://github.com/tkejzlar/aquatemp/pull/1) by [@cmoine](https://github.com/cmoine)
- Log the cloud's `error_code` / `error_msg` at WARNING level when login fails

## [3.0.41] - 2026-04-29

_Released in [tkejzlar/aquatemp](https://github.com/tkejzlar/aquatemp)_

### Changed

- Fall back to all devices on the account when none matches the `PRODUCT_IDS` allow-list

## [3.0.40] - 2026-04-26

_Released in [tkejzlar/aquatemp](https://github.com/tkejzlar/aquatemp)_

### Fixed

- "Config entry was never loaded" errors when unloading after a partial setup failure

## [3.0.39] - 2026-04-26

_Released in [tkejzlar/aquatemp](https://github.com/tkejzlar/aquatemp)_

### Fixed

- Integration staying unloaded when DNS is not ready during Home Assistant boot

## [3.0.38] - 2026-04-26

_Released in [tkejzlar/aquatemp](https://github.com/tkejzlar/aquatemp)_

### Fixed

- Login failing with valid credentials because the options flow dropped the API type, falling back to the legacy endpoint
- Network and parsing errors reported as "Invalid credentials"
- Retries sleeping 1000 seconds instead of 1 second, which hung setup and service calls
- "Already been setup" errors after a failed setup attempt
- No recovery from partial failures: now re-logs in, and marks entities unavailable when the cloud is unreachable

## 3.0.37

- Initialize data using `async_request_refresh` instead of `async_config_entry_first_refresh` to remove warning message

## 3.0.36

- Add support for more products [PR #83](https://github.com/radical-squared/aquatemp/pull/83) by [@Know1](https://github.com/Know1)

## 3.0.35

- Fix minimum / maximum values according to HVAC mode

## 3.0.34

- Fix relative path of config files

## 3.0.33

- Fix "detected blocking call to open inside the event loop by custom integration" error

## 3.0.32

- Fix warning - StrEnum is a deprecated alias which will be removed in HA Core 2025.5. Use enum.StrEnum instead

## 3.0.31

- Disable climate backwards compatibility flag

## 3.0.30

- Fix error message `implicitly supporting turn_on/turn_off` introduced in v2024.2

## 3.0.29

- Replaced soon (2025) to get deprecated SUPPORT\_\* constant with ClimateEntityFeature

## 3.0.28

_Minimum HA Version: 2024.1.0b0_

- Set minimum HA version for component to 2024.1.0b0

## 3.0.27

_Minimum HA Version: 2024.1.0_

- Adjust code to HA 2024.1.0

## v3.0.26

- Change API update from 30 seconds to 5 minutes, will update also when action is being performed
- Redact sensitive details from diagnostic file
- Fix diagnostic file creation process

## v3.0.25

### Breaking Change!

Password store format changed, up until now, password saved as the hash being send to the API,

To allow the enhanced functionality added, to edit Credentials and API Type, the password is now being saved encrypted and decrypted in 2 flows:

1. Edit integration details
2. On startup (hashed and sent to the API)

As result of that process, you need to re-setup the integration.

### Changes

- Add to set up configuration form new field of title to define the name of the integration
- Add edit integration details - Title, Credentials and API Type
- Refactor component initialization code to simplify process
- Fix `UndefinedType._singleton` name for climate entity

## v3.0.24

- Add missing configuration for API param 'error_code'

## v3.0.23

- Fix APIParam class, caused corrupted data on component creation and error code handling

## v3.0.22

- Fix binary sensor state evaluation

## v3.0.21

- Fix vacuum entity name
- Fix add integration (config) error handling

## v3.0.20

- Fix error handling when performing an action
- Optimize components loading

## v3.0.19

- Fix error handling when fetch data failed

## v3.0.18

- Add more parameters to API type configuration
- Extract model for HA DeviceInfo from API
- Add translation key to all components with name ready for translation

## v3.0.17

- Fix logic to extract protocol codes
- Fix mappings of product ID 1442284873216843776

## v3.0.16

- Optimize error handling for fetch device data

## v3.0.15

- Add log to update device

## v3.0.14

- Fix for the new capability of AquaTemp of single app to login, will re-login on every attempt to perform action / refresh
- Add new binary sensor of `API Status` represents whether the API is authenticated (logged in) or not

## v3.0.13

- Add API Type drop-down to configuration (Aqua Temp, Hitemp, Aqua Temp [=<1.5.8])
- Update authentication process

## v3.0.12

- Fix config flow, API manager constructor requires three parameters but only two are passed when creating it

## v3.0.11

- Per device's product ID parameters support

## v3.0.10

- Handling expired token error (401) more gracefully (re-login)

## v3.0.9

- Add support for product ID `1245226668902080512` [#25](https://github.com/radical-squared/aquatemp/issues/25)

## v3.0.8

- Fix missing `Off` mode for climate

## v3.0.7

- Improve support for devices of product ID `1442284873216843776`

## v3.0.6

- Fix device's empty values as `None` handling

## v3.0.5

- Set device's empty values as `None`

## v3.0.4

- Add device discovery for new devices without need to reload integration
- Fix integration reload issue
- Entities code clean up
- API stabilization after timeout
- Fix target temperature parameter mapping (Heat, Cool and Auto)
- Fix parameter mapping for P01 (Water pump mode)

## v3.0.3

- Fix setting HVAC mode
- Support shared devices
- Support multiple product IDs, Solution provided by [sjtrny](https://github.com/sjtrny) for issue [#25](https://github.com/radical-squared/aquatemp/issues/25)

## v3.0.2

- Fix configuration saving, without credentials
- Fix socket timeouts
- Add `suggested_unit_of_measurement=UnitOfElectricPotential.VOLT` to sensors of `SensorDeviceClass.VOLTAGE`
- Fix token clean-up
- Code clean up for entities
- HVAC Mode Mapping in v3.0.1 is mixed up [#29](https://github.com/radical-squared/aquatemp/issues/29)
- Block API operations if initial login failed

## v3.0.1

- Refactor entity's creation (using EntityDescription)
- Mapped all protocol codes to `EntityDescription`
- Add more entities (updated list in README)
- Create [Protocol Codes](https://github.com/radical-squared/aquatemp/blob/master/PROTOCOL_CODES.md) document
- Fix `climate` HVAC Modes

## v3.0.0

- Major refactor to the code - Breaking changes
- Configuration is available only from UI
- Supports multiple accounts (different credentials)
- Supports multiple devices (different devices on the same account)
- Add centralized `DataUpdateCoordinator` to communicate with the API and post updates to HA components
- Set minimum and maximum temperature based on the current HVAC mode relevant for the device (from API)
- Add `diagnostic` component to output data from API and configuration for troubleshooting (replacing the need for extra codes attributes)
- Add `binary_sensor` components for Power (Is on), Status (Is online) and Fault (Has fault)
- Add `select` component for choosing the Temperature Unit (C/F)
- Add `sensor` components for each of the temperature reading (T01-T03)
- Simplified `climate` component to include just its functionality without additional attributes (moved to dedicated components)
- Add mapping of more Protocol Codes (Parameters) for later support of more sensors/binary_sensors

[Unreleased]: https://github.com/MatiasFernandez/aquatemp/compare/v3.1.0...HEAD
[3.1.0]: https://github.com/MatiasFernandez/aquatemp/compare/b163b69...v3.1.0
[3.0.43]: https://github.com/tkejzlar/aquatemp/compare/07b9856...b163b69
[3.0.42]: https://github.com/tkejzlar/aquatemp/compare/7d6e14b...07b9856
[3.0.41]: https://github.com/tkejzlar/aquatemp/compare/2bfffe4...7d6e14b
[3.0.40]: https://github.com/tkejzlar/aquatemp/compare/a01fa08...2bfffe4
[3.0.39]: https://github.com/tkejzlar/aquatemp/compare/10d398a...a01fa08
[3.0.38]: https://github.com/tkejzlar/aquatemp/compare/27e4fe9...10d398a
