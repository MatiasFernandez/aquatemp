# Home Assistant Aqua Temp & Hi Temp Heat Pumps

[![Validate](https://github.com/MatiasFernandez/aquatemp/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/MatiasFernandez/aquatemp/actions/workflows/validate.yml)
[![Coverage](https://codecov.io/gh/MatiasFernandez/aquatemp/branch/main/graph/badge.svg)](https://codecov.io/gh/MatiasFernandez/aquatemp)
[![Release](https://img.shields.io/github/v/release/MatiasFernandez/aquatemp)](https://github.com/MatiasFernandez/aquatemp/releases)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories/)
[![Home Assistant](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2FMatiasFernandez%2Faquatemp%2Fmain%2Fhacs.json&query=%24.homeassistant&prefix=%E2%89%A5%20&label=Home%20Assistant&logo=homeassistant&color=41BDF5)](https://www.home-assistant.io/)

Home Assistant integration for PHNIX heat pumps controlled through the Aqua Temp or HiTemp cloud. It adds a thermostat for each heat pump (target temperature, HVAC mode and fan mode) and sensors for the parameters the device reports.

> **This is a fork** of [tkejzlar/aquatemp](https://github.com/tkejzlar/aquatemp), itself a fork of [radical-squared/aquatemp](https://github.com/radical-squared/aquatemp). It evolves independently and has its own releases; upstream changes are merged in occasionally. What this fork changes is listed in the [changelog](CHANGELOG.md), starting with 3.1.0, its first release.

Using a heat pump model other than the maintainer's? [Tell us how it works](#help-improve-support-for-your-model).

[Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md)

## Before you install

You need an account in the Aqua Temp or HiTemp app with your heat pump on it.

The cloud allows **one login per account at a time**: when Home Assistant logs in, the app on your phone is logged out, and the other way around. To use both, create a second account in the app, share the heat pump with it from your main account, and give Home Assistant one of the two accounts.

## Installation

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=MatiasFernandez&repository=aquatemp&category=integration)

1. Click the button above, or in HACS add the custom repository `MatiasFernandez/aquatemp` as an integration.
2. Download "Aqua Temp" and restart Home Assistant.
3. Go to Settings → Devices & Services → Add Integration and pick "Aqua Temp", or click:

[![Open your Home Assistant instance and start setting up Aqua Temp.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=aqua_temp)

This fork uses the same integration domain (`aqua_temp`) as upstream and its other forks, so only one of them can be installed at a time. To switch, remove the other repository's download in HACS, then download this one and restart; existing configuration entries are kept.

## Configuration

| Field    | Description                                                                               |
| -------- | ----------------------------------------------------------------------------------------- |
| Title    | Name of the config entry. Defaults to "Aqua Temp".                                        |
| Username | The email address you log in to the app with, exactly as registered (no trailing spaces). |
| Password | The app password.                                                                         |
| API type | Which backend the account is on, by the app you use (below).                              |

| API type            | Use it for                                                                                                                                                                         |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Aqua Temp           | The current Aqua Temp app.                                                                                                                                                         |
| HiTemp              | The HiTemp app. Today it reaches the same backend as Aqua Temp.                                                                                                                    |
| Aqua Temp (<=1.5.8) | Accounts on the legacy backend used by Aqua Temp app versions up to 1.5.8. The server still responds, but this option hasn't been tested recently; only try it if the others fail. |

You can add several config entries, one per account, and each account can have several heat pumps. To change the credentials or API type later, open the integration's **Configure** dialog.

The integration polls the cloud every 5 minutes, and right after each change made from Home Assistant. The cloud takes 4 to 5 minutes to notice that a heat pump went offline, but shows it back online within seconds.

> [!NOTE]
> **Password longer than 16 characters?** The Aqua Temp app (seen in version 2.1.5) silently keeps only the first 16 characters of the password, both when the account is created and at every login, so the account's real password may be shorter than the one you type. This integration uses the full password as entered and hashes it for login, since that behavior could change. If a longer password fails with "Invalid credentials" but works in the app, enter only its first 16 characters.

The **Configure** dialog also has **Log session token**, for debugging the cloud API by hand: it writes the API session token to the Home Assistant log once per login. The token is a credential (anyone holding it can control your heat pump until the next login), so turn it off before sharing logs.

## What you get

Each heat pump becomes a Home Assistant device, named after its nickname in the app, with its model as reported by the cloud. It gets:

| Entity           | Platform      | Description                                                                                                        |
| ---------------- | ------------- | ------------------------------------------------------------------------------------------------------------------ |
| (device name)    | climate       | Target temperature, HVAC mode and fan mode. The modes depend on the model (see below).                             |
| Fault            | binary_sensor | On when the cloud reports a fault; the `fault` attribute holds its description.                                    |
| Status           | binary_sensor | Whether the device is online. It may not update on the current Aqua Temp backend.                                  |
| API Status       | binary_sensor | Whether the integration is logged in to the cloud.                                                                 |
| Temperature Unit | select        | The unit Home Assistant reads the heat pump's values in. Set it to match the device; it doesn't change the device. |
| Water ΔT         | sensor        | Outlet minus inlet water temperature, on models whose profile maps both.                                           |
| Refresh Data     | button        | Polls the cloud now instead of waiting for the next update. Stays available after a failed update, to retry.       |

Plus one sensor per parameter in the model's profile: temperatures, pressures, frequencies, valve positions and so on. Which profile a heat pump gets depends on its product ID:

| Product ID          | Profile                                                                                                          | HVAC modes            | Fan modes      |
| ------------------- | ---------------------------------------------------------------------------------------------------------------- | --------------------- | -------------- |
| 1245226668902080512 | Hitemp ([parameters](custom_components/aqua_temp/cloud/profiles/entity_description.1245226668902080512.json))    | off, heat             | off, low, high |
| 1442284873216843776 | Aqua Temp ([parameters](custom_components/aqua_temp/cloud/profiles/entity_description.1442284873216843776.json)) | off, cool, heat, auto | auto, low      |
| Any other           | Default ([parameters](custom_components/aqua_temp/cloud/profiles/entity_description.default.json))               | off, cool, heat, auto | auto, low      |

The integration picks up the heat pumps on the account whose product ID is on its list of known heat pumps ([`PRODUCT_IDS`](custom_components/aqua_temp/cloud/consts.py)). If none of them matches, it takes every device on the account. New heat pumps on the account show up without reloading the integration.

## Troubleshooting

### Logs and diagnostics

For debug logs, go to Settings → Devices & Services → Aqua Temp → ⋮ → **Enable debug logging**, reproduce the problem, then **Disable debug logging**: the browser downloads the log. Or add this to `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.aqua_temp: debug
```

The **diagnostics** file (Settings → Devices & Services → Aqua Temp → ⋮ → **Download diagnostics**) holds the device's raw data and the entities created from it, which is often the quickest way to diagnose a problem. Before attaching it to a public issue, open it and check it holds nothing you don't want to share.

### Invalid credentials

- Use the email address as the username, exactly as registered.
- Check the API type matches your app.
- Password longer than 16 characters? Try its first 16 characters: see the [note above](#configuration).

### Invalid token

The form shows "Corrupted encryption key" when the integration can't decrypt the stored password. The encryption key lives in `.storage/aqua_temp.config.json`, under `data.key`. To recover:

1. Remove the integration.
2. Delete `.storage/aqua_temp.config.json`.
3. Restart Home Assistant.
4. Add the integration again.

If it still happens, [open an issue](https://github.com/MatiasFernandez/aquatemp/issues/new/choose).

## Help improve support for your model

The integration builds on one used by hundreds of installations, and its changes are checked against the official app, so it should work across the heat pumps the app supports. The maintainer can only test on one unit, though, so reports from other models are what tell us it does.

- **It works on your model?** Say so in the pinned ["Which heat pumps work?"](https://github.com/MatiasFernandez/aquatemp/discussions/18) discussion. One line with the brand, model and app is enough.
- **Something is wrong or missing?** Open a [bug report](https://github.com/MatiasFernandez/aquatemp/issues/new?template=bug_report.yml), ideally with the diagnostics file. A sensor that reports nothing or a wrong value, or a mode that does nothing on your model, is worth reporting even if you can't dig into it. If the values are mapped wrong, the steps below help.
- **Have an idea or a question?** Start a [discussion](https://github.com/MatiasFernandez/aquatemp/discussions).

### Data from mobile app

If mapping for your device are incorrect, please follow the steps below before reporting an issue:

1. Install on your mobile device packet sniffer (I'm using for Android - NetCapture)
2. Activate the packet sniffer just for the app
3. Open the app
4. Login
5. Open relevant device
6. Open menu
7. Click on `Parameter Settings`
8. First cycle, use password for user parameters, code: `022`
9. Take screenshot of each screen (letter)
10. Repeat steps 8 & 9 with code `066` - factory parameters
11. Open packet sniffer app and extract requests (and responses) of `login`, `deviceList`, `getDataByCode`

Attach the following details to issue:

- Mobile App name and version
- Attach screenshots and logs as zip file or link for download
- Attach diagnostic details from HA integration

Pull requests are welcome too: see [CONTRIBUTING.md](CONTRIBUTING.md). They should come with tests where possible; the suite runs offline against a mocked cloud.

## Acknowledgements

Originally written by [radical-squared](https://github.com/radical-squared/aquatemp), then rewritten by [Elad Bar](https://github.com/elad-bar) and maintained by [tkejzlar](https://github.com/tkejzlar/aquatemp). The cloud protocol was first worked out by [dst6se/aquatemp](https://github.com/dst6se/aquatemp).

Thanks to [@dodg3r](https://github.com/dodg3r) and [@kopierschnitte](https://github.com/kopierschnitte) for the [second-account workaround](https://github.com/radical-squared/aquatemp/issues/53) to the one-login limit.
