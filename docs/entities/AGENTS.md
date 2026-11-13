# Entity reference

Reference pages where a user looks up an entity by its name in Home Assistant and learns, quickly, what it is and how sure we are of it. Readers are heat pump owners, not contributors.

## Structure

- [README.md](README.md) maps heat pumps to pages and defines the confidence levels. Keep it short.
- One page per device class (`pool-heat-pumps.md`, ...), matching the classes in [classes.json](../../custom_components/aqua_temp/cloud/profiles/classes.json). Add a row to the README table for each new page.
- Each page opens with an index table of every entity, sorted alphabetically by name, with its topic and confidence.
- Entries are grouped under `##` topics an owner or installer recognises: Operation, Temperatures, Faults and protections, Wired inputs, and parameter families as the controller groups them (Defrost, Expansion valve, Fan, System, Water pump, ...). Never group by how the integration reads a value (bit codes, request fields, catalogs).

## Entries

Every entry follows the same pattern:

```markdown
### <Name as Home Assistant shows it>

<Entity type> · <enabled | disabled by default[, diagnostic]>[ · Aqua Temp API type only] · **<Verified | Inferred | Unknown>**

One or two sentences: what it is and what its states mean, in plain words.

<details><summary>How we know</summary>

The evidence, with links. Then the contributor details:

Code: `<cloud code>`, <how it is read, and how that differs between products>.

</details>
```

- The heading is the entity's name exactly as Home Assistant shows it, so GitHub's anchor matches the index link.
- Add `Aqua Temp API type only` when the entry's catalog entry is requested through `bitCodes`, or otherwise needs a field only that API type has.
- Keep the visible part as short as it needs to be. Implementation details (codes, polarity, product IDs, fixtures) go inside **How we know**, never above it.
- Say what we don't know in the visible part when it changes how a user reads the entity, e.g. "which state means it has tripped is unknown".
- Confidence uses only the three levels defined in the README, with the same words everywhere. An entity whose catalog entry has `"verified": false` is Inferred or Unknown, never Verified. When the evidence changes, update the level, the index row and the evidence together.

## Evidence

- Cite only public sources: the official app's behaviour ("the official app shows ..."), files in this repo (recorded fixtures, profile files), and public vendor documents with page numbers.
- Keep entries in step with the profiles in [cloud/profiles/](../../custom_components/aqua_temp/cloud/profiles/): when a change renames an entity, changes its polarity or default, or adds one, update its entry in the same change.
