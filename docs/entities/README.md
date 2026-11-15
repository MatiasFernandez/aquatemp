# Entities

What each entity the integration creates means, and how sure we are of it. Look up an entity by the name Home Assistant shows.

## Which page applies to your heat pump

Entities depend on your heat pump's product ID, shown in the device's diagnostics.

| Heat pumps                                                                                                                                         | Page                                  |
| -------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------- |
| Pool heat pumps: the 30 product IDs listed under `pool_heat_pump` in [classes.json](../../custom_components/aqua_temp/cloud/profiles/classes.json) | [Pool heat pumps](pool-heat-pumps.md) |

Other heat pumps aren't documented yet.

## How to read an entry

Each entry starts with the entity's type, whether it is enabled by default, the API type it needs if not every one gets it, and how sure we are of what it means:

- **Verified**: the official Aqua Temp app shows or acts on it the same way, or we've watched the value change on a real unit.
- **Inferred**: worked out from vendor documentation or the name the cloud gives it. The entry says from what.
- **Unknown**: the integration reads it, but we don't know what its values mean on these units.

An entry marked **Aqua Temp API type only** is created only on accounts using the Aqua Temp API type, shown in the device's diagnostics. The other API types can't ask the cloud for its value, so on them the entity doesn't appear.

Under **How we know**, each entry gives the evidence, and the details only contributors need: the cloud's code for the value and how it differs between products.
