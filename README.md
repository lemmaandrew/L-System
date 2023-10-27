# L-System

Create [L-System](https://en.wikipedia.org/wiki/L-system) images using this handy-dandy CLI tool.

Must be run on Python 3.10+.

More information in `main.py`'s help text.

Example:  
`python3 main.py -rules X "F+[[XU]D-XU]D-F[-FXU]D+X" F FF --seed "D++X" --height 768 --width 1366 --rotatedeg 25 --movelen 0.35 --penwidth 1 --startx 0 --starty 768 --pencolors 5bcefa f5a9b8 ffffff f5a9b8 fbcefa` results in:

![Barnsley fern in trans flag colors](examples/trans_barnsley_fern.png)
