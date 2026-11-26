# House style

Every recipe is rewritten into this one format. The model is Martha Stewart's recipe conventions.

## The rule above all others

You may change wording. You may never change facts. Every quantity, temperature, time, pan size, and yield must be exactly what the source says. Do not add ingredients, steps, or claims that are not in the source. Do not convert units: metric stays metric, US stays US.

## Title

Title case, no trailing punctuation, no site names or words like "Best" or "Easy" unless they are part of the dish's name.

## Headnote

One or two sentences about the dish. If the source has an introduction or description, condense it and set `headnote_from_source` to true. If it has none, write one plain sentence using only facts found in the recipe and set `headnote_from_source` to false. No hype and no invented history.

## Yield and times

- `yield_label` is "Serves" for portions and "Makes" for counted or measured output. `yield_value` is the rest: "8", "24", "About 2 cups".
- `active_minutes` is hands-on time (the source may call it prep time). `total_minutes` is start to finish. Use null when the source does not say; never estimate.

## Ingredients

- One ingredient per line, in order of use.
- Line shape: quantity, unit, ingredient, then preparation after a comma. "2 tablespoons unsalted butter, softened".
- Spell units out: tablespoon, teaspoon, cup, ounce, pound. Never "tbsp" or "c."
- Container sizes go in parentheses after the unit: "1 can (15 ounces) pure pumpkin purée".
- Helpful equivalents may stay in parentheses when the source gives them: "8 tablespoons (1 stick) unsalted butter".
- Lines with no quantity start with a capital: "Pinch of coarse salt", "Vanilla ice cream, for serving".
- Use groups ("For the crust", "For the filling") only when the source has clearly separate components. Otherwise use one group with a null name.
- Use the preferred ingredient names from the glossary.

## Directions

- One continuous list of steps. Plain imperative sentences. Drop articles where natural: "Whisk together flour and salt."
- Where a new component starts, give the step a short `lead` such as "Make the topping". Otherwise `lead` is null. Do not put the lead inside `text`.
- State the oven temperature where the oven is first needed, as "Preheat oven to 375 degrees." That is the first step unless something chills or rests first.
- Ranges use "to": "50 to 60 minutes".
- Do not number the steps in the text.

## Cook's note

Storage, make-ahead, and substitution advice from the source, in one short paragraph. Empty string when the source has none.

## Category and tags

Pick the one category from the list given that fits best. Suggest up to four short tags for season, occasion, or diet, only when the recipe clearly supports them.
