"""Sample recipes of four lengths, already in house style."""

from recipebook.model import Recipe, Source
from recipebook.style.housestyle import apply_house_style
from recipebook.web.forms import parse_ingredients, parse_steps


def _build(**kw) -> Recipe:
    kw["ingredient_groups"] = parse_ingredients(kw.pop("ingredients"))
    kw["steps"] = parse_steps(kw.pop("directions"))
    return apply_house_style(Recipe(**kw))


def short() -> Recipe:
    return _build(
        id=157, title="Maple Whipped Cream", category="Desserts & Baking",
        headnote="A spoonful of maple syrup sweetens the cream and gives it a faint caramel note. "
                 "Whip it just before serving, or see the note to make it ahead.",
        yield_label="Makes", yield_value="About 2 cups", active_minutes=5, total_minutes=15,
        source=Source(kind="web", url="https://example.com/maple-whipped-cream"),
        ingredients="1 cup heavy cream, well chilled\n2 tablespoons pure maple syrup\n"
                    "½ teaspoon pure vanilla extract\nPinch of coarse salt",
        directions="Chill a large metal bowl and a whisk in the freezer 10 minutes.\n\n"
                   "Combine cream, maple syrup, vanilla, and salt in chilled bowl. Whisk until soft peaks form, "
                   "2 to 3 minutes; do not overbeat. Serve immediately.",
        note="Whipped cream can be made up to 4 hours ahead; cover and refrigerate. Whisk briefly to restore "
             "its texture before serving.",
    )


def medium() -> Recipe:
    return _build(
        id=142, title="Apple-Cranberry Crisp with Pecan-Oat Topping", category="Desserts & Baking",
        headnote="Tart cranberries keep this fall crisp from tipping too sweet, and a generous pecan-oat topping "
                 "bakes up crunchy enough to stand up to a scoop of vanilla ice cream.",
        yield_value="8", active_minutes=25, total_minutes=105,
        source=Source(kind="other", label="Handwritten family recipe card"),
        ingredients="""For the topping:
¾ cup all-purpose flour
¾ cup old-fashioned rolled oats
½ cup packed light-brown sugar
½ cup pecans, coarsely chopped
½ teaspoon ground cinnamon
¼ teaspoon coarse salt
8 tablespoons (1 stick) unsalted butter, melted
For the filling:
3 pounds firm, tart apples (about 6), such as Granny Smith, peeled, cored, and cut into ½-inch slices
2 cups fresh or frozen cranberries
½ cup granulated sugar
2 tablespoons fresh lemon juice
2 tablespoons all-purpose flour
1 teaspoon ground cinnamon
¼ teaspoon freshly grated nutmeg
Pinch of coarse salt
Vanilla ice cream, for serving""",
        directions="""Preheat oven to 375 degrees. Butter a 9-by-13-inch baking dish.

Make the topping: In a medium bowl, stir together flour, oats, brown sugar, pecans, cinnamon, and salt. Drizzle in melted butter and mix with your fingers until large clumps form. Refrigerate while you make the filling.

Make the filling: In a large bowl, toss apples, cranberries, granulated sugar, lemon juice, flour, cinnamon, nutmeg, and salt until evenly coated. Transfer to prepared dish and spread in an even layer.

Scatter topping evenly over filling. Set dish on a rimmed baking sheet and bake until topping is deep golden brown and juices are bubbling at the edges, 50 to 60 minutes. If topping browns too quickly, tent loosely with foil.

Let cool on a wire rack at least 20 minutes before serving with ice cream.""",
        note="The crisp can be assembled up to 1 day ahead; cover and refrigerate, then bake straight from the "
             "refrigerator, adding 5 to 10 minutes. Leftovers keep, covered, at room temperature for up to 2 days.",
    )


def long() -> Recipe:
    return _build(
        id=118, title="Pumpkin Layer Cake with Maple Cream Cheese Frosting", category="Desserts & Baking",
        headnote="Buttermilk keeps the crumb tender, and a whole can of pumpkin means nothing goes to waste. "
                 "Bake the layers a day ahead; they are easier to frost once they have rested.",
        yield_value="12", active_minutes=45, total_minutes=180,
        source=Source(kind="cookbook", title="Sample Cookbook", author="A. N. Author", page="112"),
        ingredients="""For the cake:
3 cups all-purpose flour, plus more for pans
2 teaspoons baking powder
1 teaspoon baking soda
1 teaspoon coarse salt
2 teaspoons ground cinnamon
1 teaspoon ground ginger
½ teaspoon freshly grated nutmeg
¼ teaspoon ground cloves
1 cup (2 sticks) unsalted butter, room temperature, plus more for pans
1½ cups packed light-brown sugar
½ cup granulated sugar
4 large eggs, room temperature
1 can (15 ounces) pure pumpkin purée
2 teaspoons pure vanilla extract
¾ cup buttermilk, room temperature
For the frosting:
12 ounces cream cheese, room temperature
½ cup (1 stick) unsalted butter, room temperature
¼ cup pure maple syrup
1 teaspoon pure vanilla extract
Pinch of coarse salt
4 cups confectioners’ sugar, sifted
For assembly:
½ cup pecans, toasted and coarsely chopped""",
        directions="""Preheat oven to 350 degrees. Butter two 9-inch round cake pans; line bottoms with parchment. Butter parchment, dust with flour, and tap out excess.

Make the cake: In a medium bowl, whisk together flour, baking powder, baking soda, salt, cinnamon, ginger, nutmeg, and cloves.

With an electric mixer on medium-high speed, beat butter and both sugars until pale and fluffy, about 4 minutes. Add eggs, one at a time, beating well after each addition and scraping down sides of bowl. Beat in pumpkin and vanilla. (Mixture may look curdled; it will come together.)

Reduce speed to low. Add flour mixture in 3 batches, alternating with buttermilk and beginning and ending with flour; mix just until combined.

Divide batter evenly between prepared pans and smooth tops. Bake, rotating pans halfway through, until a cake tester inserted in centers comes out clean, 32 to 36 minutes. Let cool in pans on a wire rack 15 minutes; turn out cakes and let cool completely, about 1 hour.

Make the frosting: Beat cream cheese and butter on medium-high speed until smooth, about 2 minutes. Beat in maple syrup, vanilla, and salt. Reduce speed to low; gradually add confectioners’ sugar, then raise speed and beat until fluffy, about 1 minute.

Assemble: Trim tops of cakes level with a serrated knife, if needed. Place one layer, cut side up, on a serving plate; spread with 1 cup frosting. Top with second layer, cut side down. Spread remaining frosting over top and sides.

Press pecans around bottom edge of cake. Refrigerate until frosting is set, at least 30 minutes. Let stand at room temperature 20 minutes before serving.""",
        note="Unfrosted layers can be wrapped well and kept at room temperature for 1 day or frozen for up to "
             "1 month. The frosted cake keeps, covered and refrigerated, for up to 3 days.",
    )


def very_long() -> Recipe:
    ingredients = "\n".join(
        f"{n} tablespoons ingredient number {n}, finely chopped and set aside" for n in range(2, 62))
    directions = "\n\n".join(
        f"Step {n}: Stir the mixture over medium heat for {n + 2} minutes, scraping the bottom of the pot, "
        "then add the next ingredient and continue to cook until everything is well combined and fragrant."
        for n in range(1, 26))
    return _build(
        id=999, title="An Extremely Long Test Recipe", category="Main Dishes",
        headnote="This recipe exists only to prove that nothing breaks when a recipe is far too long.",
        yield_value="20", active_minutes=240, total_minutes=480,
        ingredients=ingredients, directions=directions, note="There is no shortcut.",
    )
