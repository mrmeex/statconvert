from dataclasses import dataclass


@dataclass
class AppContext:
    """
    Runtime application settings.
    """

    debug: bool = False

    verbose: bool = False

    use_color: bool = True


context = AppContext()