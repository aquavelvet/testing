# A5 template mockup

Approved visual reference for the recipe book templates. Not app code.

- `A5-template-set.pdf`: the rendered set (cover, contents, section divider, long recipe spread, standard recipe, short recipe, index).
- `book.css`, `book.html.j2`: the styles and template that produced it. Starting point for the real templates.
- `build.py`: the script that rendered it, with sample recipes and sample contents data.

To re-render, `build.py` expects the three font families (Cormorant Garamond, Source Serif 4, Jost) from the `@fontsource` npm packages in `../fontpkgs/node_modules`, plus `weasyprint`, `jinja2`, and `segno`. The real app will bundle full font files instead.

Mockup-only shortcuts that the real app must not copy: fixed page numbers on the divider and index pages, a hand-set type size on the crisp recipe, and a hand-set count of notes lines. The app computes all three.
