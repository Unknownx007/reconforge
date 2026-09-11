# ============================================================
#  File: reconforge/banner.py
# ============================================================
import random
import sys
from colorama import Fore, Style, init as _init
_init(autoreset=True)

R  = Fore.RED
G  = Fore.GREEN
C  = Fore.CYAN
Y  = Fore.YELLOW
M  = Fore.MAGENTA
W  = Fore.WHITE
D  = Style.DIM
B  = Style.BRIGHT
X  = Style.RESET_ALL

# ---- DEDSEC quotes -------------------------------------------------
QUOTES = [
    "We are DEDSEC. We are the ghost in the machine.",
    "They watch us. We watch them back.",
    "Information wants to be free. We just help it along.",
    "The system is not broken. The system is the break.",
    "You cannot arrest an idea.",
    "Every lock is just a puzzle waiting to be solved.",
    "We don't break in. We were never locked out.",
    "Knowledge is the only weapon that cannot be confiscated.",
    "The network remembers everything. So should you.",
    "ctOS sees all. DEDSEC sees ctOS.",
    "Privacy is not a privilege. It is a right we take back.",
    "In a world of watchers, be the ghost.",
    "Hack the planet. Free the people.",
    "The best firewall is the one they never see coming.",
    "We are not criminals. We are the immune system.",
]

LOGO = r"""
   ██████╗ ███████╗ ██████╗ ██████╗ ███╗   ██╗
   ██╔══██╗██╔════╝██╔════╝██╔═══██╗████╗  ██║
   ██████╔╝█████╗  ██║     ██║   ██║██╔██╗ ██║
   ██╔══██╗██╔══╝  ██║     ██║   ██║██║╚██╗██║
   ██║  ██║███████╗╚██████╗╚██████╔╝██║ ╚████║
   ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝
   ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
   ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
   █████╗  ██║   ██║██████╔╝██║  ███╗█████╗
   ██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝
   ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
   ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝
"""

LOGO_SMALL = r"""
  ┌─────────────────────────────────────────────┐
  │   R E C O N F O R G E   //   D E D S E C    │
  └─────────────────────────────────────────────┘
"""


def random_quote() -> str:
    return random.choice(QUOTES)


def _c(text: str, color: str) -> str:
    return f"{color}{text}{X}"


def print_banner(version: str = "1.0.0", show_quote: bool = True) -> None:
    """Print the main RECONFORGE banner."""
    sys.stdout.write("\n")
    print(_c(LOGO, R))
    print(_c("        F O R G E   //   R E C O N   S U I T E", C + B))
    print(_c("        ─────────────────────────────────────────────", D))
    print(_c(f"        version {version}   ·   built by DEDSEC   ·   "
             f"ghost in the machine", G))
    print(_c("        ─────────────────────────────────────────────", D))
    if show_quote:
        print(_c(f'        » "{random_quote()}"', Y + D))
    print()


def print_small_banner() -> None:
    print(_c(LOGO_SMALL, R))


def print_quote() -> None:
    print(_c(f'  » "{random_quote()}"  — DEDSEC', Y))


def rule(char: str = "─", width: int = 64, color: str = D) -> None:
    print(_c(char * width, color))


def step(title: str) -> None:
    print()
    print(_c(f"┌──[ {title.upper()} ]" + "─" * max(0, 50 - len(title)), C + B))


def step_end() -> None:
    print(_c("└" + "─" * 62, C + B))
