# Cloud API

This folder documents what we know about the Aqua Temp cloud API, as a [Bruno](https://www.usebruno.com/) collection in its YAML format: one request per endpoint, ready to send, with notes in each request's **Docs** tab. Folder Docs tabs cover what the requests in them share.

## How far to trust each note

Notes are marked by where the knowledge stands:

- **Probed**: seen in live API responses, on the date given. The vendor can change the backend at any time, so an old date is worth re-checking.
- **From the integration**: what the integration's cloud client ([client.py](../../custom_components/aqua_temp/cloud/client.py), paths in [endpoints.py](../../custom_components/aqua_temp/cloud/endpoints.py)) sends and expects. The integration works against the live API, so take this as the API's behaviour, but nobody probed it separately.

When you probe something, add what you saw under **Probed** with the date, and correct any note it contradicts.

| Folder                 | Contents                                                                               |
| ---------------------- | -------------------------------------------------------------------------------------- |
| `01 Auth`              | login, user info                                                                       |
| `02 Devices`           | owned devices, accepted shares, pending shares                                         |
| `03 Device Data`       | getDataByCode and its v5 variant, status, faults                                       |
| `04 Control`           | power, target temperature, HVAC mode, fan mode. **These write to the real heat pump.** |
| `05 Device Parameters` | the device's own parameter lists, with labels, ranges and option labels                |

## Setup

Install Bruno (`brew install --cask bruno` on macOS), then **Open Collection** and pick this folder. The collection is in Bruno's YAML format (`opencollection.yml` at the root), which older Bruno releases can't open. Once:

1. Select the **aqua-temp** environment (top right).
2. In the environment settings, fill `user_name` (the login email) and `password` (plaintext). Leave the other secrets empty: the requests fill them.

Keep certificate verification on: the server's certificate validates. If every request fails with a network error, check the certificate (`curl https://cloud.linked-go.com:449`); an expired one is the vendor's to renew.

The account has one session at a time: logging in here logs out the app or Home Assistant on the same account, and logging in there ends the session here.

## Use

1. **01 Auth / Login** hashes the password with MD5 and stores the returned `x-token`. Every request sends it as the `x-token` header, set in [opencollection.yml](opencollection.yml).
2. **01 Auth / Get User Info** stores `user_id`, which the two device share lists send as `toUser`.
3. **02 Devices / Device List** stores the first device's `device_code` and `device_id`, if `device_code` is still empty. If the heat pump is shared with your account rather than owned by it, run **Shared Devices (accepted)** instead: it stores them the same way.

The requests in `03 Device Data` and `04 Control` are then ready; `05 Device Parameters` runs in the order its Docs tab gives. An `"error_code": "-100"` response means the token expired or the path doesn't exist; run Login again.

To probe parameters, edit the `protocol_codes` environment variable and run **03 Device Data / Get Data By Code**. A code the device doesn't know still comes back, with an empty `value` and an empty `dataType`; that request's notes have the details.

If the login script fails (it hashes with Bruno's built-in `crypto-js`), remove the script and put the digest of the whole password straight into the body. This reads the password without echoing it or saving it in your shell history:

```bash
read -rs password && printf '%s' "$password" | md5    # macOS
read -rs password && printf '%s' "$password" | md5sum # Linux: the digest is the first 32 characters
unset password
```

A password longer than 16 characters hashed whole fails with `1400034`; see Login's notes.

## API variants

The integration knows three API types, each described by a profile in [custom_components/aqua_temp/cloud/profiles/](../../custom_components/aqua_temp/cloud/profiles/). The collection targets the current one, which [api.aqua_temp.json](../../custom_components/aqua_temp/cloud/profiles/api.aqua_temp.json) and [api.hi_temp.json](../../custom_components/aqua_temp/cloud/profiles/api.hi_temp.json) share: same host, same field names. HiTemp accounts work with it unchanged.

The legacy [api.aqua_temp_old.json](../../custom_components/aqua_temp/cloud/profiles/api.aqua_temp_old.json) isn't covered. It uses another host (`cloud.linked-go.com/cloudservice/api`), appends `.json` to every path and spells every field in snake_case (`device_code`, `protocal_codes`, `object_result`), so it would need its own set of requests. Login on the current host doesn't recognise its `user_name` field.

`protocalCodes`, `protocalId`, `tranferUnit`, `Appect` and `Tobe` are the API's own spellings.

## Secrets

[environments/aqua-temp.yml](environments/aqua-temp.yml) lists `user_name`, `password`, `token`, `user_id`, `device_code` and `device_id` with `secret: true`: Bruno keeps their values on your machine and only the names are in the file. Check `git diff` before committing changes to the collection anyway, and don't paste real values into request bodies or docs. Responses from Device List and Query Device By Id include the device's `deviceSecret`; keep them out of issues and commits too.
