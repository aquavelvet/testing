"""Mockup only: renders the A5 template set (cover, contents, divider, recipes, index) to one PDF.

Recipes below are original sample text. Contents and index entries are sample data that
show what a full book would look like; page numbers are set to match them.
"""
from pathlib import Path
from itertools import groupby

import jinja2
import segno
import weasyprint

HERE = Path(__file__).parent
OUT = HERE.parent / "A5-template-set.pdf"

book = dict(
    kicker="A Family Cookbook",
    title="Recipes from Our Kitchen",
    title_html="Recipes from<br>Our Kitchen",
    subtitle="Collected, tested, and written down",
    edition="2026 Edition",
)

toc = [
    dict(name="Breakfast & Brunch", page=5, recipes=[
        ("Buttermilk Pancakes", 6), ("Baked Eggs with Spinach and Gruyère", 7),
        ("Overnight Cinnamon Rolls", 8), ("Cheddar-Chive Scones", 10)]),
    dict(name="Starters & Soups", page=11, recipes=[
        ("Roasted Tomato Soup", 12), ("Whipped Feta with Honey", 13),
        ("Butternut Squash Soup with Sage", 14), ("Spiced Mixed Nuts", 15)]),
    dict(name="Main Dishes", page=17, recipes=[
        ("Roast Chicken with Lemon and Thyme", 18), ("Weeknight Turkey Chili", 20),
        ("Baked Rigatoni with Sausage", 21), ("Pan-Seared Salmon with Dill", 22),
        ("Braised Short Ribs with Red Wine", 24)]),
    dict(name="Salads & Sides", page=27, recipes=[
        ("Kale Salad with Apples and Pecans", 28), ("Garlic Mashed Potatoes", 29),
        ("Roasted Brussels Sprouts with Bacon", 30), ("Cornbread Stuffing", 31)]),
    dict(name="Desserts & Baking", page=33, recipes=[
        ("Pumpkin Layer Cake with Maple Cream Cheese Frosting", 34),
        ("Apple-Cranberry Crisp with Pecan-Oat Topping", 36),
        ("Maple Whipped Cream", 37), ("Classic Pecan Pie", 38),
        ("Gingerbread Cookies", 39), ("No-Knead Crusty Bread", 40)]),
]
index_page = 42

divider = dict(part="Part Five", title_html="Desserts<br>&amp; Baking", page=33, recipes=toc[-1]["recipes"])

qr_url = "https://example.com/maple-whipped-cream"
qr_uri = segno.make(qr_url, error="m").svg_data_uri(border=0, dark="#2b2b2b", scale=4)

recipes = [
    dict(
        layout="spread", id="118", category="Desserts & Baking",
        title="Pumpkin Layer Cake with Maple Cream Cheese Frosting",
        headnote="Buttermilk keeps the crumb tender, and a whole can of pumpkin means nothing goes to waste. "
                 "Bake the layers a day ahead; they are easier to frost once they have rested.",
        yield_label="Serves", yield_value="12", active="45 minutes", total="3 hours",
        source="Source: Sample Cookbook, by A. N. Author, page 112",
        groups=[
            dict(name="For the cake", items=[
                "3 cups all-purpose flour, plus more for pans",
                "2 teaspoons baking powder",
                "1 teaspoon baking soda",
                "1 teaspoon coarse salt",
                "2 teaspoons ground cinnamon",
                "1 teaspoon ground ginger",
                "½ teaspoon freshly grated nutmeg",
                "¼ teaspoon ground cloves",
                "1 cup (2 sticks) unsalted butter, room temperature, plus more for pans",
                "1½ cups packed light-brown sugar",
                "½ cup granulated sugar",
                "4 large eggs, room temperature",
                "1 can (15 ounces) pure pumpkin purée",
                "2 teaspoons pure vanilla extract",
                "¾ cup buttermilk, room temperature",
            ]),
            dict(name="For the frosting", items=[
                "12 ounces cream cheese, room temperature",
                "½ cup (1 stick) unsalted butter, room temperature",
                "¼ cup pure maple syrup",
                "1 teaspoon pure vanilla extract",
                "Pinch of coarse salt",
                "4 cups confectioners’ sugar, sifted",
            ]),
            dict(name="For assembly", items=[
                "½ cup pecans, toasted and coarsely chopped",
            ]),
        ],
        steps=[
            dict(lead=None, text="Preheat oven to 350 degrees. Butter two 9-inch round cake pans; line bottoms with "
                 "parchment. Butter parchment, dust with flour, and tap out excess."),
            dict(lead="Make the cake", text="In a medium bowl, whisk together flour, baking powder, baking soda, salt, "
                 "cinnamon, ginger, nutmeg, and cloves."),
            dict(lead=None, text="With an electric mixer on medium-high speed, beat butter and both sugars until pale "
                 "and fluffy, about 4 minutes. Add eggs, one at a time, beating well after each addition and scraping "
                 "down sides of bowl. Beat in pumpkin and vanilla. (Mixture may look curdled; it will come together.)"),
            dict(lead=None, text="Reduce speed to low. Add flour mixture in 3 batches, alternating with buttermilk and "
                 "beginning and ending with flour; mix just until combined."),
            dict(lead=None, text="Divide batter evenly between prepared pans and smooth tops. Bake, rotating pans "
                 "halfway through, until a cake tester inserted in centers comes out clean, 32 to 36 minutes. Let cool "
                 "in pans on a wire rack 15 minutes; turn out cakes and let cool completely, about 1 hour."),
            dict(lead="Make the frosting", text="Beat cream cheese and butter on medium-high speed until smooth, about "
                 "2 minutes. Beat in maple syrup, vanilla, and salt. Reduce speed to low; gradually add confectioners’ "
                 "sugar, then raise speed and beat until fluffy, about 1 minute."),
            dict(lead="Assemble", text="Trim tops of cakes level with a serrated knife, if needed. Place one layer, cut "
                 "side up, on a serving plate; spread with 1 cup frosting. Top with second layer, cut side down. Spread "
                 "remaining frosting over top and sides."),
            dict(lead=None, text="Press pecans around bottom edge of cake. Refrigerate until frosting is set, at least "
                 "30 minutes. Let stand at room temperature 20 minutes before serving."),
        ],
        note="Unfrosted layers can be wrapped well and kept at room temperature for 1 day or frozen for up to 1 month. "
             "The frosted cake keeps, covered and refrigerated, for up to 3 days.",
        notes_lines=0, qr=None,
    ),
    dict(
        layout="page", id="142", category="Desserts & Baking", font_size="8.2pt",
        title="Apple-Cranberry Crisp with Pecan-Oat Topping",
        headnote="Tart cranberries keep this fall crisp from tipping too sweet, and a generous pecan-oat topping bakes "
                 "up crunchy enough to stand up to a scoop of vanilla ice cream.",
        yield_label="Serves", yield_value="8", active="25 minutes", total="1 hour 45 minutes",
        source="Source: Handwritten family recipe card",
        groups=[
            dict(name="For the topping", items=[
                "¾ cup all-purpose flour",
                "¾ cup old-fashioned rolled oats",
                "½ cup packed light-brown sugar",
                "½ cup pecans, coarsely chopped",
                "½ teaspoon ground cinnamon",
                "¼ teaspoon coarse salt",
                "8 tablespoons (1 stick) unsalted butter, melted",
            ]),
            dict(name="For the filling", items=[
                "3 pounds firm, tart apples (about 6), such as Granny Smith, peeled, cored, and cut into ½-inch slices",
                "2 cups fresh or frozen cranberries",
                "½ cup granulated sugar",
                "2 tablespoons fresh lemon juice",
                "2 tablespoons all-purpose flour",
                "1 teaspoon ground cinnamon",
                "¼ teaspoon freshly grated nutmeg",
                "Pinch of coarse salt",
                "Vanilla ice cream, for serving",
            ]),
        ],
        steps=[
            dict(lead=None, text="Preheat oven to 375 degrees. Butter a 9-by-13-inch baking dish."),
            dict(lead="Make the topping", text="In a medium bowl, stir together flour, oats, brown sugar, pecans, "
                 "cinnamon, and salt. Drizzle in melted butter and mix with your fingers until large clumps form. "
                 "Refrigerate while you make the filling."),
            dict(lead="Make the filling", text="In a large bowl, toss apples, cranberries, granulated sugar, lemon "
                 "juice, flour, cinnamon, nutmeg, and salt until evenly coated. Transfer to prepared dish and spread in "
                 "an even layer."),
            dict(lead=None, text="Scatter topping evenly over filling. Set dish on a rimmed baking sheet and bake until "
                 "topping is deep golden brown and juices are bubbling at the edges, 50 to 60 minutes. If topping "
                 "browns too quickly, tent loosely with foil."),
            dict(lead=None, text="Let cool on a wire rack at least 20 minutes before serving with ice cream."),
        ],
        note="The crisp can be assembled up to 1 day ahead; cover and refrigerate, then bake straight from the "
             "refrigerator, adding 5 to 10 minutes. Leftovers keep, covered, at room temperature for up to 2 days.",
        notes_lines=0, qr=None,
    ),
    dict(
        layout="page", id="157", category="Desserts & Baking",
        title="Maple Whipped Cream",
        headnote="A spoonful of maple syrup sweetens the cream and gives it a faint caramel note. Whip it just "
                 "before serving, or see the note to make it ahead.",
        yield_label="Makes", yield_value="About 2 cups", active="5 minutes", total="15 minutes",
        source="Source: example.com/maple-whipped-cream",
        groups=[
            dict(name=None, items=[
                "1 cup heavy cream, well chilled",
                "2 tablespoons pure maple syrup",
                "½ teaspoon pure vanilla extract",
                "Pinch of coarse salt",
            ]),
        ],
        steps=[
            dict(lead=None, text="Chill a large metal bowl and a whisk in the freezer 10 minutes."),
            dict(lead=None, text="Combine cream, maple syrup, vanilla, and salt in chilled bowl. Whisk until soft "
                 "peaks form, 2 to 3 minutes; do not overbeat. Serve immediately."),
        ],
        note="Whipped cream can be made up to 4 hours ahead; cover and refrigerate. Whisk briefly to restore its "
             "texture before serving.",
        notes_lines=9, qr=qr_uri,
    ),
]

# Alphabetical index built from the sample contents
titles = sorted(((t, p) for cat in toc for t, p in cat["recipes"]), key=lambda x: x[0].lower())
index = [(letter, list(items)) for letter, items in groupby(titles, key=lambda x: x[0][0].upper())]

env = jinja2.Environment(loader=jinja2.FileSystemLoader(HERE), autoescape=True, trim_blocks=True, lstrip_blocks=True)
html = env.get_template("book.html.j2").render(
    book=book, toc=toc, index_page=index_page, divider=divider, recipes=recipes, index=index)
(HERE / "book.html").write_text(html)

doc = weasyprint.HTML(string=html, base_url=str(HERE)).render()
doc.write_pdf(OUT)
print("pages:", len(doc.pages), "->", OUT.name)
