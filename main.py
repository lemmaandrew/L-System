#!/usr/bin/env python3

from argparse import ArgumentParser, Namespace, RawDescriptionHelpFormatter
from dataclasses import dataclass
from enum import IntEnum, auto
from math import ceil, cos, floor, pi, radians, sin
from typing import Callable, Sequence

from PIL import Image, ImageDraw


class Command(IntEnum):
    PENDOWN = auto()
    PENUP = auto()
    MOVEFORWARD = auto()
    ROTATECCW = auto()
    ROTATECW = auto()
    STOREPOS = auto()
    GOTOPOS = auto()
    NOACTION = auto()


NamedCommand = tuple[str, Command]


@dataclass
class Cursor:
    x: float
    y: float
    angle: float
    is_down: bool

    def move_forward(self, movement_length: float):
        """Moves the cursor forward in the direction it is facing"""
        self.x += movement_length * cos(self.angle)
        # subtract because need to reverse up and down from sin
        self.y -= movement_length * sin(self.angle)

    def rotate_ccw(self, radians: float):
        self.angle += radians

    def rotate_cw(self, radians: float):
        self.angle -= radians


class LSystem:
    def __init__(
        self,
        seed: list[NamedCommand],
        rules: dict[NamedCommand, list[NamedCommand]],
        canvas_width: int,
        canvas_height: int,
        start_x: int | None = None,
        start_y: int | None = None,
        background_color: tuple[int, int, int] = (0, 0, 0),
        pen_colors: Sequence[tuple[int, int, int]] = ((0xFF, 0xFF, 0xFF),),
        movement_length: float = 5.0,
        pen_thickness: int = 5,
        rotate_angle: float = pi / 2.0,
    ):
        self.seed = seed
        self.rules = rules
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.background_color = background_color
        self.pen_colors = pen_colors
        self.gradient = LSystem.build_color_gradient(self.pen_colors)
        self.movement_length = movement_length
        self.pen_thickness = pen_thickness
        self.rotate_angle = rotate_angle

        self.canvas = Image.new(
            "RGB", (self.canvas_width, self.canvas_height), background_color
        )
        self.canvas_draw = ImageDraw.Draw(self.canvas)
        self.system_value = seed.copy()
        self.saved_cursors: list[Cursor] = []
        self.cursor = Cursor(
            self.canvas_width // 2 if start_x is None else start_x,
            self.canvas_height // 2 if start_y is None else start_y,
            0.0,
            True,
        )

    @staticmethod
    def build_rules(
        rules_map: dict[str, str], names_map: dict[str, Command]
    ) -> dict[NamedCommand, list[NamedCommand]]:
        """Build a named rules engine out of a map of X -> Y rules (`rules_map`)
        and names for each singular command (`names_map`)
        """
        for k in rules_map.keys():
            if len(k) != 1:
                raise ValueError(f"Rules map key {k} must have length 1")
        for k in names_map.keys():
            if len(k) != 1:
                raise ValueError(f"Rules map key {k} must have length 1")

        rules = dict[NamedCommand, list[NamedCommand]]()
        for k, vs in rules_map.items():
            rules[(k, names_map[k])] = [(v, names_map[v]) for v in vs]
        return rules

    @staticmethod
    def build_color_gradient(
        colors: Sequence[tuple[int, int, int]]
    ) -> Callable[[float], tuple[int, int, int]]:
        """Builds a function which continuously linearly interpolates between the given colors.
        The returned function takes a parameter in the domain [0.0, 1.0], and returns a color along the created curve.
        """
        if not colors:
            raise ValueError("Must have at least one color")
        for r, g, b in colors:
            if not (0 <= r <= 0xFF and 0 <= g <= 0xFF and 0 <= b <= 0xFF):
                raise ValueError(f"{(r, g, b)} is not a valid RGB triple")

        def lerp(a: float, b: float, t: float) -> float:
            """Linear interpolation from a to b"""
            return a + t * (b - a)

        def scale_t(t_min: float, t_max: float, t: float) -> float:
            """Scales t from its original bounds of two color locations [t_min, t_max] to [0.0, 1.0]"""
            return (t - t_min) / (t_max - t_min)

        def gradient(t: float) -> tuple[int, int, int]:
            """Finds the color at f(t) along the interpolated curve.
            t must be a value in the domain [0.0, 1.0].
            """
            if len(colors) == 1:
                return colors[0]
            # clipping to domain of [0.0, 1.0]
            t = max(min(t, 1.0), 0.0)
            n = len(colors) - 1
            x = t * n
            i = floor(x)
            j = ceil(x)
            if i == j:
                return colors[i]
            # need to scale t such that t is between color1 and color2 (t_min and t_max)
            t_min = i / n
            t_max = j / n
            scaled_t = scale_t(t_min, t_max, t)
            r1, g1, b1 = colors[floor(x)]
            r2, g2, b2 = colors[ceil(x)]
            r = int(lerp(r1, r2, scaled_t))
            g = int(lerp(g1, g2, scaled_t))
            b = int(lerp(b1, b2, scaled_t))
            return r, g, b

        return gradient

    def count_draws(self) -> int:
        """Counts the number of draw commands that the system value will create.
        Used for color interpolation
        """
        pen_is_down = self.cursor.is_down
        draws = 0
        for _, command in self.system_value:
            match command:
                case Command.PENDOWN:
                    pen_is_down = True
                case Command.PENUP:
                    pen_is_down = False
                case Command.MOVEFORWARD:
                    if pen_is_down:
                        draws += 1
                case Command.GOTOPOS:
                    if pen_is_down:
                        draws += 1
                case _:
                    pass
        return draws

    def iterate_system_value(self) -> None:
        """Iterates the system's value, modifying `self.system_value`"""
        new_system_value: list[NamedCommand] = []
        for named_command in self.system_value:
            if named_command in self.rules:
                new_system_value.extend(self.rules[named_command])
            else:
                new_system_value.append(named_command)
        self.system_value = new_system_value

    def run_system_value(self) -> None:
        """Updates the canvas and the cursor according to the current system value"""

        def draw(from_x: float, from_y: float, to_x: float, to_y: float):
            nonlocal draws, total_draws
            """Draws a line from (from_x, from_y) to (to_x, to_y)"""
            color = self.gradient(draws / total_draws)
            self.canvas_draw.line(
                ((from_x, from_y), (to_x, to_y)),
                fill=color,
                width=self.pen_thickness,
            )

        draws = 0
        total_draws = self.count_draws()
        for _, command in self.system_value:
            match command:
                case Command.PENDOWN:
                    self.cursor.is_down = True
                case Command.PENUP:
                    self.cursor.is_down = False
                case Command.MOVEFORWARD:
                    from_x = self.cursor.x
                    from_y = self.cursor.y
                    self.cursor.move_forward(self.movement_length)
                    if self.cursor.is_down:
                        to_x = self.cursor.x
                        to_y = self.cursor.y
                        draw(from_x, from_y, to_x, to_y)
                        draws += 1
                case Command.ROTATECCW:
                    self.cursor.rotate_ccw(self.rotate_angle)
                case Command.ROTATECW:
                    self.cursor.rotate_cw(self.rotate_angle)
                case Command.STOREPOS:
                    self.saved_cursors.append(self.cursor)
                case Command.GOTOPOS:
                    saved_cursor = self.saved_cursors.pop()
                    if self.cursor.is_down:
                        draw(
                            self.cursor.x, self.cursor.y, saved_cursor.x, saved_cursor.y
                        )
                        draws += 1
                    saved_cursor.is_down = self.cursor.is_down
                    self.cursor = saved_cursor
                case _:
                    pass

    def iterate_n_then_run(self, n: int):
        """Iterates the L-System `n` times then runs it"""
        for _ in range(n):
            self.iterate_system_value()
        self.run_system_value()


def process_arguments(args: Namespace) -> LSystem:
    """Processes command line arguments"""

    def process_hex_string(hex_str: str) -> tuple[int, int, int]:
        if len(hex_str) != 6:
            raise ValueError("Color string must be length 6")
        return int(hex_str[:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)

    DEFAULT_NAMES = {
        "F": Command.MOVEFORWARD,
        "G": Command.MOVEFORWARD,
        "H": Command.MOVEFORWARD,
        "X": Command.NOACTION,
        "Y": Command.NOACTION,
        "Z": Command.NOACTION,
        "+": Command.ROTATECCW,
        "-": Command.ROTATECW,
        "[": Command.STOREPOS,
        "]": Command.GOTOPOS,
        "U": Command.PENUP,
        "D": Command.PENDOWN,
    }
    str_rules = dict[str, str](zip(args.rules[::2], args.rules[1::2]))
    rules_map = LSystem.build_rules(str_rules, DEFAULT_NAMES)
    seed: list[NamedCommand] = [
        (command, DEFAULT_NAMES[command]) for command in args.seed
    ]
    pen_colors = list(map(process_hex_string, args.pencolors))
    background_color = process_hex_string(args.bgcolor)
    return LSystem(
        seed,
        rules_map,
        args.width,
        args.height,
        args.startx,
        args.starty,
        background_color,
        pen_colors,
        args.movelen,
        args.penwidth,
        radians(args.rotatedeg),
    )


def main():
    description = """Generate an image from an L-System.
Currently supported named commands are:
    "F": Move forward, can also be used to store more complex rules
    "G": Move forward, can also be used to store more complex rules
    "H": Move forward, can also be used to store more complex rules
    "+": Rotate counter-clockwise
    "-": Rotate clockwise
    "U": Lift drawing pen up (stop drawing)
    "D": Put drawing pen down (resume drawing)
    "[": Store position and angle onto stack
    "]": Remove most recent position and angle from stack and move cursor there
    "X": No action, used for storing more complex rules
    "Y": No action, used for storing more complex rules
    "Z": No action, used for storing more complex rules
Cursor begins facing to the right
"""
    parser = ArgumentParser(
        description=description, formatter_class=RawDescriptionHelpFormatter
    )
    rules_help = (
        "Rules engine for L-System. Named command first, then the rule it defines."
        " For example, the Barnsley fern rule system would be '--rules X \"F+[[XU]D-XU]D-F[-FXU]D+X\" F FF'"
    )
    parser.add_argument("--rules", type=str, nargs="+", help=rules_help, required=True)
    seed_help = "Seed value for L-System. For example, the Barnsley fern seed would be '--seed \"++X\"'"
    parser.add_argument("--seed", type=str, help=seed_help, required=True)
    parser.add_argument(
        "--height", type=int, help="Image height in pixels", required=True
    )
    parser.add_argument(
        "--width", type=int, help="Image width in pixels", required=True
    )
    parser.add_argument(
        "--startx",
        type=int,
        help="Starting x position of cursor (default middle of image)",
        default=None,
    )
    parser.add_argument(
        "--starty",
        type=int,
        help="Starting y position of cursor (default middle of image)",
        default=None,
    )
    parser.add_argument(
        "--movelen",
        type=float,
        help="Pen movement length per forward command (default 5.0)",
        default=5.0,
    )
    parser.add_argument(
        "--penwidth", type=int, help="Pen width in pixels (default 1)", default=1
    )
    parser.add_argument(
        "--rotatedeg",
        type=float,
        help="Amount in degrees to rotate when + and - commands are used (default 90 degrees)",
        default=90.0,
    )
    parser.add_argument(
        "--bgcolor",
        type=str,
        help="Background color hex string (default '000000')",
        default="000000",
    )
    parser.add_argument(
        "--pencolors",
        type=str,
        nargs="+",
        help="Pen colors in series of hex strings (default ['FFFFFF'])",
        default=["FFFFFF"],
    )
    parser.add_argument(
        "--numiters",
        type=int,
        help="Number of iterations of L-System to perform before drawing (default 10)",
        default=10,
    )

    args = parser.parse_args()
    lsystem = process_arguments(args)
    lsystem.iterate_n_then_run(args.numiters)
    lsystem.canvas.show()


if __name__ == "__main__":
    main()
