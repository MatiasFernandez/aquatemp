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

- **Verified**: the entry says only what we observed: the official Aqua Temp app shows or acts on the value the same way, or we've watched it change on a real unit. On an entity holding several values, such as the climate entity, a narrower part resting on our reading is marked as ours in the text.
- **Inferred**: the entry states a conclusion we drew ourselves, from the app's behaviour, vendor documentation, the name the cloud gives the value or other products. The evidence is real, but nobody has confirmed the conclusion and it could be wrong. The entry says which part is our reading and what it rests on.
- **Unknown**: the integration reads it, but we have no basis for what its values mean on these units, so the entity shows the raw value.

An entry marked **Aqua Temp API type only** is created only on accounts using the Aqua Temp API type, shown in the device's diagnostics. The other API types can't ask the cloud for its value, so on them the entity doesn't appear.

Under **How we know**, each entry gives the evidence, and the details only contributors need: the cloud's code for the value and how it differs between products.
