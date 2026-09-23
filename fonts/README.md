# Bundled fonts

The six font files named by `theme.json` are retained without modification:

| Family | Version from font metadata | Files |
|---|---|---|
| DejaVu Sans | 2.37 | `DejaVuSans.ttf`, `DejaVuSans-Bold.ttf`, `DejaVuSans-Oblique.ttf`, `DejaVuSans-BoldOblique.ttf` |
| Noto Emoji | 3.005 | `NotoEmoji-Regular.ttf`, `NotoEmoji-Bold.ttf` |

DejaVu's [upstream license](https://dejavu-fonts.github.io/License.html) covers
Bitstream Vera and Arev contributions, with DejaVu changes in the public domain.
[dejavu-sans/LICENSE.txt](dejavu-sans/LICENSE.txt) reproduces the full license text
embedded in all four retained files, including the Bitstream and Tavmjong Bah notices.

Noto Emoji's metadata identifies Copyright 2013 Google LLC and the SIL Open Font
License 1.1. [noto-emoji/OFL.txt](noto-emoji/OFL.txt) reproduces the matching
[upstream license](https://github.com/googlefonts/noto-emoji/blob/main/LICENSE).
These font licenses are separate from the application's MIT license.

When packaging the game, include these six files at their existing relative paths,
`theme.json`, and both license notices. The loader resolves asset paths from the
application directory or PyInstaller's bundle directory. pygame_gui also supplies
its own fallback fonts; those dependency assets are separate from this directory.
