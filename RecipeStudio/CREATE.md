# Create recipe modules — working notes

Target: Minecraft 1.21.1, KubeJS 2101, Create 6.0.10.
This file is the source of truth for the Create phase. Keep it updated when a
detail is clarified.

---

## New reusable components

### Burner / heat level

Three visual states:

| Level | Icon | Meaning |
| --- | --- | --- |
| none | `create:empty_blaze_burner` | no heat |
| heated | `create:blaze_burner` | heated |
| superheated | `create:blaze_cake` | superheated |

Used by compacting and mixing (under the basin). It should be a small reusable
widget with a tooltip and a click/cycle action.

### Expanding ingredient group

A row/column of slots that always ends with one empty slot. Adding an item to
the empty slot appends a new empty slot at the end. The group has a configurable
limit, e.g. 8 entries.

Used by:

- compacting item inputs
- compacting fluid inputs
- chance outputs
- haunting inputs
- splashing inputs
- mixing item/fluid inputs and outputs
- sequenced-assembly scraps
- similar multi-input/multi-output recipes

### Fluid amount field

A number field for fluids. Right-click cycles the wheel step:

1. `1 mb`
2. `snap 50 mb`
3. `snap 1 B` (`1000 mb`)

The stored value is always in mB. Display should make the unit and current snap
obvious. Used wherever `Fluid.of(id, amount)` appears.

### Chance output slot / chance group

Slot displays the chance in the top-right corner. Mouse wheel over the slot
changes the count as usual. `Alt+wheel` changes chance:

- `0.001 … 0.01` in steps of `0.001`
- `0.01 … 1.0` in steps of `0.01`

Chance is in `(0, 1]`. Codegen for 1.21.1 uses `CreateItem.of('id', chance)`.
Chance outputs are grouped with the expanding group component.

### Syntax switch (backlog, not required for first pass)

Export panel switch:

- `1.21.1` — default
- `1.20.1`

Some Create/KubeJS syntax differs between these versions. Keep codegen
version-aware so this can be added later without rewriting every module.

---

## Recipe modules

### Compacting

- Tab icon: Create basin (`create:basin`).
- Layout: mechanical press, then the basin; item and fluid input groups between
  them; chance output group.
- Supports item counts and fluids.
- Heat control under the basin (same burner component as mixing).
- Inputs: expanding item group + expanding fluid group.
- Outputs: expanding chance group.

### Crushing

- Tab icon: Create crushing wheels (`create:crushing_wheel`).
- Layout: slots between two crushing wheels.
- Input: exactly one item.
- Output: expanding chance group.

### Cutting

- Tab icon: Create saw (`create:mechanical_saw`).
- Input: exactly one item.
- Output: expanding chance group.

### Deploying

- Tab icon: Create deployer (`create:deployer`).
- Layout: depot with the input item; deployer above it with the held item.
- Right side: expanding chance output group.
- Checkbox: `keepHeldItem`.
- Inputs: depot item + deployer held item.

### Emptying

- Tab icon: Create mechanism icon (TBD: item drain / relevant Create machine).
  The user described it as “their mechanism (uses the <>)”.
- Supports fluid output.
- Input: item (container).
- Outputs: item + fluid.
- Read the Create guide for exact `type`/field names.

### Filling

- Opposite of emptying.
- Supports fluid input.
- Inputs: item + fluid.
- Output: item.

### Haunting

- Tab icon: soul campfire (`minecraft:soul_campfire` or Create equivalent).
- Input: expanding item group with counts.
- Output: expanding chance group.
- No fluid support unless the guide says otherwise.

### Splashing

- Tab icon: water bucket (`minecraft:water_bucket`).
- Input: expanding item group with counts.
- Output: expanding chance group.
- Same shape as haunting; different recipe type.

### Bulk smelting / bulk blasting (“обжарка и плавка”)

- Follow the same cooking-style visual as vanilla smelting/blasting, but with
  Create fan processing semantics.
- Check the Create docs/exported recipes for the exact type names and fields
  (`create:bulk_smelting`, `create:bulk_blasting`, or equivalent).
- Input: one item; output: one item; cooking time if supported.

### Mechanical crafting

- Tab icon: mechanical crafter (`create:mechanical_crafter`).
- Grid `n × m`, with buttons to increase/decrease width and height.
- Maximum `9 × 9`, minimum `1 × 1`.
- Behaves like crafting, but outputs a stack (not a chance group).
- Output slot supports count.

### Milling

- Tab icon: millstone (`create:millstone`).
- Weaker version of crushing; place before crushing in tab order.
- Layout: one input item slot + expanding chance output group.
- Do not show two millstones.

### Mixing

- Tab icon: Create mixer / basin mechanism.
- Supports fluids.
- Heat control under the basin (same burner component as compacting).
- Inputs: expanding item stack group + expanding fluid group.
- Outputs: expanding fluid group + expanding chance group.

### Pressing

- Tab icon: mechanical press (`create:mechanical_press`).
- Input: one item.
- Output: expanding chance group.

### Sandpaper polishing

- Tab icon: sandpaper (`create:sandpaper`).
- Input: one item.
- Output: one item with chance.

### Mystical conversion

- Not implemented. Skip entirely.

### Sequenced assembly (hardest)

- Tab icon: belt (`create:belt` / belt connector).
- Left side, two item slots with labels:
  - `Starting item`
  - `Transitional item`
- When the starting item is set, automatically copy it into the transitional
  item slot.
- Bottom: one output slot with chance, plus a “remaining / scrap” expanding
  chance group.
- Center: ordered sequence of steps. Add step types:
  - pressing
  - cutting
  - deploying
  - “what was on the spout with fluids” (filling/emptying — confirm exact
    Create sequence step types)
- Each step displays the icon of its mechanism.
  - Deployer step: item slot for the held item.
  - Spout step: fluid slot / fluid amount field.
- Bottom numeric spinner: number of loops.
- Everything needs a visible label.

---

## Open questions / things to confirm from the Create guide

1. Exact `event.custom({...})` field names for every Create recipe type.
2. 1.21.1 vs 1.20.1 syntax differences, especially `CreateItem.of`.
3. Emptying/filling tab icons and whether “uses the <>” means item drain or
   spout.
4. Exact sequenced-assembly step schema and the spout step variant.
5. Whether bulk smelting/blasting use `cookingTime` or Create processing time.
6. How fluid outputs express amounts and chances in 1.21.1.

---

## Confirmed syntax from `../kubejs/all_crafts/create/*.js`

All Create recipes except mechanical crafting are emitted as `event.custom({...})`.

Common fields:

```js
event.custom({
  ingredients: [
    { item: 'minecraft:copper_ore' },
    { tag: 'c:ingots/brass' },
    { type: 'neoforge:single', fluid: 'create:tea', amount: 250 },
    // or: { type: 'neoforge:components', fluids: '...', components: {}, amount: 1000 }
  ],
  results: [
    { id: 'create:crushed_raw_copper', count: 5 },
    { id: 'create:crushed_raw_copper', chance: 0.25 },
    { id: 'create:experience_nugget', chance: 0.75 },
    { id: 'dndesires:strawberry_milkshake', amount: 250 },
  ],
  processing_time: 250,          // crushing/cutting/milling
  heat_requirement: 'heated',    // compacting/mixing, also 'superheated'
  keep_held_item: true,          // deploying
  type: 'create:crushing',
});
```

Notes:

- Item stack: `{ id, count }`; chance output: `{ id, chance }`; fluid output:
  `{ id, amount }` (fluid outputs look like items with an `amount`).
- Fluid ingredient variants seen: `neoforge:single` with `fluid`, and
  `neoforge:components` with `fluids` + `components: {}`. Use `neoforge:single`.
- `mechanical_crafting` is exported by the old editor as `event.shaped(...)`.
  Remote docs give the proper dedicated syntax:
  `event.recipes.create.mechanical_crafting(output, pattern[], key{})`.
  We will use that for grids larger than 3×3.
- `sequenced_assembly` fields:
  `sequence: []`, `results: []`, `loops`, `ingredient`,
  `transitional_item: { id: ... }`, `type`.
  Each sequence step is a nested recipe object (`create:pressing`,
  `create:cutting`, `create:deploying`, etc.).
- Heat values: `heat_requirement: 'heated'` and `'superheated'`; no field for
  unheated.

## Implementation order

1. Shared components: burner, expanding group, fluid amount, chance slot.
2. Simple one-input/one-output modules: pressing, cutting, milling, sandpaper.
3. Two-input modules: deploying, emptying, filling.
4. Group/fluid modules: compacting, mixing, haunting, splashing.
5. Mechanical crafting (large grid).
6. Sequenced assembly last.
7. Optional 1.20.1 syntax switch.

## Status (implemented)

All shared widgets and modules above are implemented, including 9×9
mechanical crafting and sequenced assembly with loops/scrap. The optional
1.20.1 syntax switch and bulk smelting/blasting remain backlog.
